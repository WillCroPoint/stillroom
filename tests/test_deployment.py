import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

import gui

ROOT=Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def test_exact_origins(self):
        for value in ['http://tower:8080','https://fraimic.example.com','http://192.168.1.10:8080']:
            self.assertEqual(gui.validate_origin(value),value)
        for value in ['*','https://example.com/','http://user:pass@example.com','http://tower:0',
                      'http://tower:99999','http://tower:bad','http://tower?x=1','http://tower#x','file:///tmp/a']:
            with self.subTest(value=value),self.assertRaises(ValueError):
                gui.validate_origin(value)

    def test_network_bind_requires_explicit_origin(self):
        env=dict(os.environ);env.pop('FRAIMIC_PUBLIC_ORIGIN',None)
        result=subprocess.run([sys.executable,str(ROOT/'gui.py'),'-n','-b','0.0.0.0'],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('--public-origin is required',result.stderr)

    def test_sigterm_cleans_temporary_images(self):
        with tempfile.TemporaryDirectory() as directory:
            env=dict(os.environ,TMPDIR=directory,STUDIO_APP_NAME='Test Studio');env.pop('FRAIMIC_PUBLIC_ORIGIN',None)
            process=subprocess.Popen([sys.executable,str(ROOT/'gui.py'),'-n','-c',str(Path(directory)/'frames.json')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                first=process.stdout.readline()
                self.assertIn('Test Studio:',first)
                # Startup writes the temporary directory before entering serve_forever.
                self.assertTrue(list(Path(directory).glob('fraimic-studio-*')))
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=10)
                self.assertEqual(process.returncode,0)
                self.assertFalse(list(Path(directory).glob('fraimic-studio-*')))
            finally:
                if process.poll() is None:
                    process.kill();process.communicate()

    def test_helper_build_before_replace_and_safe_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'deploy/docker').mkdir(parents=True)
            (root/'bin').mkdir()
            shutil.copy(ROOT/'deploy/manage.sh',root/'deploy/manage.sh')
            (root/'deploy/docker/.env').write_text('GIT_REMOTE=fork\nGIT_BRANCH=customization\nPUID=1000\nPGID=1000\n')
            (root/'bin/docker').write_text('#!/bin/sh\necho "docker $*" >> "$TRACE"\ncase "$*" in *"build --pull"*) exit "${BUILD_EXIT:-0}";; esac\n')
            (root/'bin/git').write_text('''#!/bin/sh
echo "git $*" >> "$TRACE"
case "$1" in
 status) printf '%s' "${DIRTY:-}" ;;
 symbolic-ref) echo customization ;;
esac
''')
            for name in ('docker','git'):(root/'bin'/name).chmod(0o755)
            trace=root/'trace'
            env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],TRACE=str(trace))
            def run(action,**extra):
                trace.write_text('')
                result=subprocess.run(['bash',str(root/'deploy/manage.sh'),action],env=dict(env,**extra),capture_output=True,text=True)
                return result,trace.read_text()
            result,log=run('start')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertLess(log.index('build --pull'),log.index('up -d --no-build'))
            result,log=run('apply')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('up -d --no-build --force-recreate',log)
            self.assertNotIn('build --pull',log)
            self.assertNotIn('git pull',log)
            result,log=run('start',BUILD_EXIT='1')
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('up -d',log)
            result,log=run('update',DIRTY=' M gui.py')
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('git pull',log)
            result,log=run('update')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('git pull --ff-only fork customization',log)
            self.assertIn('up -d --no-build',log)
            self.assertNotIn('down',log)


if __name__=='__main__':unittest.main()
