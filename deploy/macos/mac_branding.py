"""Build-time identity and runtime display-name overrides for the Mac wrapper."""
import os
from pathlib import Path
import plistlib
import sys

from branding import DEFAULT_APP_NAME, load_app_name


def build_name(environ=None):
    environ = os.environ if environ is None else environ
    name = load_app_name(environ={'STUDIO_APP_NAME':
        environ.get('MACOS_APP_NAME') or DEFAULT_APP_NAME})
    if name in ('.', '..') or any(c in name for c in '/:'):
        raise ValueError('macOS application names cannot contain / or : or be . or ..')
    return name


def bundle_name():
    if getattr(sys, 'frozen', False):
        with (Path(sys.executable).parent.parent / 'Info.plist').open('rb') as stream:
            return plistlib.load(stream)['CFBundleName']
    return DEFAULT_APP_NAME


def window_name(directory):
    config = directory / 'branding.local.json'
    if config.exists() or os.environ.get('STUDIO_APP_NAME'):
        return load_app_name(config)
    return bundle_name()
