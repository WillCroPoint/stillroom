"""Display identity shared by the server and future desktop packaging."""
import json
import os
from pathlib import Path

DEFAULT_APP_NAME = 'Stillroom'
LOCAL_CONFIG = Path(__file__).resolve().with_name('branding.local.json')


def load_app_name(config_path=LOCAL_CONFIG, environ=None):
    """Environment overrides private local settings; public builds use the default."""
    environ = os.environ if environ is None else environ
    name = environ.get('STUDIO_APP_NAME')
    if not name:
        path = Path(config_path)
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or set(data) != {'app_name'}:
                raise ValueError('Branding configuration must contain only app_name.')
            name = data['app_name']
        else:
            name = DEFAULT_APP_NAME
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
            or any(not c.isprintable() for c in name)):
        raise ValueError('Application name must contain 1–80 printable characters.')
    return name.strip()
