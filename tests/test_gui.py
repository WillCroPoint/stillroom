import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from PIL import Image

import gui

FRAME = {'id': 'test-frame', 'name': 'Test frame', 'host': 'fraimic.local', 'screen': '133', 'orientation': 'landscape'}


def image_bytes():
    image = Image.new('RGB', (120, 80), 'red')
    image.paste('blue', (60, 0, 120, 80))
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


class GUIImageTests(unittest.TestCase):
    def test_crop_anchors_rotation_and_bands(self):
        small = gui.converter.Panel('small', 'test', 12, 20, 120, None)
        image = Image.open(io.BytesIO(image_bytes()))
        frame = dict(FRAME, orientation='portrait')
        with patch.dict(gui.converter.PANELS, {'133': small}):
            for x, color in [(0, (255,0,0)), (1, (0,0,255))]:
                settings = gui.validate_settings(dict(profile='natural', x=x, zoom=2, brightness=1, contrast=1, saturation=1))
                result = gui.compose_image(image, frame, settings)
                self.assertEqual(result.size, (12,20))
                self.assertEqual(result.getpixel((6,10)), color)
            settings = gui.validate_settings(dict(fit='letterbox', letterbox='white'))
            result = gui.compose_image(image, frame, settings)
            self.assertEqual(result.getpixel((0,0)), (255,255,255))
            for rotation in (0,90,180,270):
                settings = gui.validate_settings(dict(rotation=rotation,brightness=1,contrast=1,saturation=1))
                result = gui.compose_image(image, FRAME, settings)
                self.assertEqual(result.size,(20,12))

    def test_image_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            studio = gui.Studio(Path(temp) / 'frames.json')
            try:
                rgba = Image.new('RGBA', (30, 20), (255, 0, 0, 0))
                raw = io.BytesIO()
                rgba.save(raw, format='PNG')
                source = studio.add_image(raw.getvalue(), 'transparent.png')
                with Image.open(studio.root / source['id'] / 'source.png') as image:
                    self.assertEqual(image.getpixel((0,0))[3], 0)
                self.assertTrue(source['transparent'])
                raw = io.BytesIO()
                rgba.save(raw, format='WEBP', lossless=True)
                source = studio.add_image(raw.getvalue(), 'transparent.webp')
                self.assertTrue(source['transparent'])
                exif = Image.Exif()
                exif[274] = 6
                raw = io.BytesIO()
                Image.new('RGB', (30,20), 'red').save(raw, format='JPEG', exif=exif)
                source = studio.add_image(raw.getvalue(), 'phone.jpg')
                self.assertEqual((source['width'],source['height']), (20,30))
                if gui.converter.HEIC_SUPPORTED:
                    import pillow_heif
                    path = Path(temp) / 'phone.heic'
                    pillow_heif.from_pillow(Image.new('RGB', (32,24), 'blue')).save(path)
                    source = studio.add_image(path.read_bytes(), path.name)
                    self.assertEqual((source['width'],source['height']), (32,24))
            finally:
                studio.close()

    def test_validation(self):
        for settings in [dict(zoom=0),dict(x=float('nan')),dict(rotation=45),dict(fit='rotate')]:
            with self.assertRaises(gui.APIError): gui.validate_settings(settings)
        for host in ['http://frame', 'frame/api', 'user@frame', 'frame:0','frame:70000']:
            with self.assertRaises(gui.APIError): gui.validate_host(host)
        for host in ['fraimic.local','192.168.1.5','127.0.0.1:12345','[::1]:8080']:
            self.assertEqual(gui.validate_host(host),host)
        with self.assertRaises(gui.APIError): gui.validate_frames({'version':1,'frames':[FRAME,FRAME]})


class GUIServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.studio = gui.Studio(Path(cls.temp.name)/'frames.json')
        cls.server = gui.ThreadingHTTPServer(('127.0.0.1',0),gui.Handler)
        cls.server.studio = cls.studio
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        root = cls.studio.root
        cls.studio.close()
        assert not root.exists()
        cls.temp.cleanup()

    def request(self,path,body=None,headers=None):
        head = {'X-Studio-Token': self.studio.token}
        head.update(headers or {})
        if body is not None and not isinstance(body,bytes): body=json.dumps(body).encode()
        with urlopen(Request(self.base+path,data=body,headers=head),timeout=10) as response:
            raw=response.read()
            return json.loads(raw) if response.headers['Content-Type']=='application/json' else raw

    def wait_job(self,key):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            job=self.request('/api/jobs/'+key)
            if job['status'] not in ('converting','sending'): return job
            time.sleep(.05)
        self.fail('Job did not finish')

    def test_end_to_end_and_failed_transfer(self):
        config=self.request('/api/config',{'version':1,'frames':[FRAME]})
        self.assertEqual(json.loads(self.studio.config_path.read_text()),config)
        self.assertEqual(self.request('/api/state')['config'],config)
        source=self.request('/api/images',image_bytes(),{'X-Filename':'photo.png'})
        self.assertEqual((source['width'],source['height']),(120,80))
        job=self.request('/api/convert',dict(source_id=source['id'],frame_id=FRAME['id'],settings={}))
        job=self.wait_job(job['id'])
        self.assertEqual(job['status'],'ready',job)
        self.assertEqual(len(self.request(job['bin'])),960000)
        with Image.open(io.BytesIO(self.request(job['preview']))) as preview:
            self.assertEqual(preview.size,(1600,1200))
            self.assertEqual(preview.getpixel((50,600)),(255,0,0))
            self.assertEqual(preview.getpixel((1550,600)),(0,0,255))
        with patch('gui.read_battery', return_value={'percent': 73, 'charging': True}) as battery, patch('gui.upload_bin', return_value=(200,'{"status":"rendering"}')) as send:
            self.request('/api/send',dict(job_id=job['id'],frame_id=FRAME['id']))
            sent=self.wait_job(job['id'])
            self.assertEqual(sent['status'],'sent')
            self.assertIn('Battery: 73% · charging',sent['message'])
            battery.assert_called_once_with(FRAME['host'])
            self.assertEqual(send.call_args.args[0],FRAME['host'])
        with patch('gui.read_battery') as battery, patch('gui.upload_bin',side_effect=OSError('Frame offline')):
            self.request('/api/send',dict(job_id=job['id'],frame_id=FRAME['id']))
            failed=self.wait_job(job['id'])
            self.assertEqual(failed['status'],'upload_error')
            self.assertIn('Frame offline',failed['message'])
            battery.assert_not_called()
            self.assertIsNone(failed['battery'])
        with patch('gui.read_battery',return_value=None) as battery, patch('gui.upload_bin',return_value=(200,'{}')):
            self.request('/api/send',dict(job_id=job['id'],frame_id=FRAME['id']))
            sent=self.wait_job(job['id'])
            self.assertEqual(sent['status'],'sent')
            self.assertIn('Battery level unavailable',sent['message'])
            battery.assert_called_once()
        self.request('/api/config',{'version':1,'frames':[dict(FRAME,orientation='portrait')]})
        with self.assertRaises(HTTPError) as error:
            self.request('/api/send',dict(job_id=job['id'],frame_id=FRAME['id']))
        self.assertEqual(error.exception.code,409)
        error.exception.close()

    def test_public_origin_keeps_host_origin_and_token_checks(self):
        self.server.public_origin='https://fraimic.example.com'
        try:
            headers={'Host':'fraimic.example.com','Origin':'https://fraimic.example.com'}
            self.assertIn('config',self.request('/api/state',headers=headers))
            # A protected write reaches validation, proving proxy headers are accepted.
            with self.assertRaises(HTTPError) as error:
                self.request('/api/config',{'bad':'config'},headers)
            self.assertEqual(error.exception.code,400)
            error.exception.close()
            for overrides in [{'Host':'evil.example'},{'Origin':'https://evil.example'},
                              {'Origin':'http://fraimic.example.com'},{'X-Studio-Token':''}]:
                with self.assertRaises(HTTPError) as error:
                    self.request('/api/config',{},dict(headers,**overrides))
                self.assertEqual(error.exception.code,403)
                error.exception.close()
            # Container health checks remain possible on loopback.
            self.assertIn('config',self.request('/api/state'))
        finally:
            self.server.public_origin=None

    def test_branding_is_escaped_and_disclaimer_is_always_visible(self):
        original = self.studio.app_name
        try:
            self.studio.app_name = 'Private <Studio> & "Friends"'
            page = self.request('/').decode()
            self.assertIn('<title>Private &lt;Studio&gt; &amp; &quot;Friends&quot;</title>', page)
            self.assertNotIn('<Studio>', page)
            self.assertNotIn('{{APP_NAME}}', page)
            self.assertIn('Not affiliated with, sponsored by, or endorsed by Fraimic.', page)
        finally:
            self.studio.app_name = original

    def test_local_request_protection_and_invalid_image(self):
        for headers in [{'X-Studio-Token':''}, {'Origin':'http://elsewhere.example'}, {'Host':'elsewhere.example'}]:
            with self.assertRaises(HTTPError) as error:
                self.request('/api/config',{'version':1,'frames':[]},headers)
            self.assertEqual(error.exception.code,403)
            error.exception.close()
        with self.assertRaises(HTTPError) as error:
            self.request('/api/images',b'bad image',{'X-Filename':'photo.png'})
        self.assertEqual(error.exception.code,400)
        error.exception.close()
        with self.assertRaises(HTTPError) as error: self.request('/media/../../gui.py')
        error.exception.close()
        self.assertIn(b'<title>Stillroom</title>',self.request('/'))
        self.assertIn(b'--accent:',self.request('/style.css'))


if __name__=='__main__': unittest.main()
