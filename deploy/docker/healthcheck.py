"""Check the local web server only. Never contact a frame."""
from urllib.request import urlopen
with urlopen('http://127.0.0.1:8080/api/state', timeout=3) as response:
    if response.status != 200:
        raise SystemExit(1)
