# Build on the target architecture. Personal configuration is never bundled.
from pathlib import Path
import sys
root = Path(SPECPATH).parents[1]
sys.path[:0] = [str(root), SPECPATH]
from mac_branding import build_name
app_name = build_name()
a = Analysis([str(Path(SPECPATH) / 'launcher.py')], pathex=[str(root)],
    datas=[(str(root / 'web'), 'web'), (str(root / 'LICENSE'), '.')],
    hiddenimports=['webview.platforms.cocoa'],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Stillroom',
    console=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name='Stillroom')
app = BUNDLE(coll, name=app_name + '.app', icon=str(root / 'web/icon.png'),
    bundle_identifier='com.willcropoint.stillroom',
    info_plist={'CFBundleName': app_name,
                'CFBundleDisplayName': app_name,
                'CFBundleShortVersionString': '0.1.0',
                'NSHighResolutionCapable': True,
                'NSLocalNetworkUsageDescription': 'Stillroom sends your images to your Fraimic frames on your local network.'})
