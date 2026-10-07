# Explicit resources keep personal frames, branding and photos out of the package.
from pathlib import Path
root = Path(SPECPATH).parents[1]
a = Analysis([str(Path(SPECPATH) / 'launcher.py')], pathex=[str(root)],
    datas=[(str(root / 'web'), 'web'), (str(root / 'LICENSE'), '.')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Stillroom',
    console=False, icon=str(root / 'web/favicon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='Stillroom')
