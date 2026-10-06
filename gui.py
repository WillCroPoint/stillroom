#!/usr/bin/env python3
"""Single-page local Fraimic editor. No web framework or JavaScript build required."""
import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
import ipaddress
import json
import math
import os
from multiprocessing import get_context
from pathlib import Path
import re
import secrets
import signal
import tempfile
from threading import RLock
import urllib.error
from urllib.parse import unquote, urlsplit
import uuid
import webbrowser

from branding import DEFAULT_APP_NAME, load_app_name
from image_background import extend_to_frame, flatten, gradient_colors, has_transparency, background_color
from PIL import Image, ImageOps
import convert_to_bin_spectra6 as converter
from decode_bin import decode
from upload import upload_bin, read_battery, battery_message

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 60 * 1024 * 1024
MAX_PIXELS = 40_000_000


def validate_origin(value):
    """An exact browser origin, including any externally published port."""
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or any(c.isspace() for c in value)):
        raise ValueError('Public origin must be http(s)://hostname[:port], without a path or trailing slash')
    # Accessing port validates its syntax/range.
    if parsed.port == 0:
        raise ValueError('Public origin port must be between 1 and 65535')
    return value


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_host(host):
    if not isinstance(host, str) or not host or len(host) > 253:
        raise APIError('Enter a hostname or IP address.')
    if any(c in host for c in '/\\@?# \t\r\n'):
        raise APIError('Use a hostname or IP, without http:// or a path.')
    try:
        parsed = urlsplit('http://' + host)
        hostname, port = parsed.hostname, parsed.port
        if not hostname or port == 0 or host.endswith(':'):
            raise ValueError()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if not re.fullmatch(r'(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?', hostname):
                raise ValueError()
    except ValueError:
        raise APIError('Invalid hostname, IP address or port.')
    return host


def validate_frames(data):
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('frames'), list):
        raise APIError('Configuration must contain version: 1 and a frames array.')
    if len(data['frames']) > 100:
        raise APIError('Too many frames (maximum 100).')
    result, ids = [], set()
    for item in data['frames']:
        if not isinstance(item, dict):
            raise APIError('Invalid frame configuration.')
        key = item.get('id') or uuid.uuid4().hex
        name = item.get('name', '')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', key) or key in ids:
            raise APIError('Frame IDs must be unique letters, numbers, underscores or hyphens.')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
            raise APIError('Give each frame a name (1–100 characters).')
        if item.get('screen') not in converter.PANELS or item.get('orientation') not in ('portrait', 'landscape'):
            raise APIError('Choose a panel model and orientation for each frame.')
        result.append(dict(id=key, name=name.strip(), host=validate_host(item.get('host')),
                           screen=item['screen'], orientation=item['orientation']))
        ids.add(key)
    return {'version': 1, 'frames': result}


def validate_settings(data):
    if not isinstance(data, dict):
        raise APIError('Invalid image settings.')
    out = {}
    for key, choices, default in [('background', ('solid', 'gradient'), 'solid'),
                                  ('fit', ('crop', 'letterbox'), 'crop'),
                                  ('letterbox', ('black', 'white'), 'black'),
                                  ('profile', tuple(converter.PROFILES), converter.DEFAULT_PROFILE),
                                  ('dither', tuple(converter.DITHERS), converter.DEFAULT_DITHER)]:
        out[key] = data.get(key, default)
        if out[key] not in choices:
            raise APIError(f'Invalid {key}.')
    try:
        out['background_color'] = background_color(data.get('background_color', '#000000' if data.get('letterbox') == 'black' else '#ffffff'))
    except ValueError as exc:
        raise APIError(str(exc))
    out['rotation'] = data.get('rotation', 0)
    if type(out['rotation']) is not int or out['rotation'] not in (0, 90, 180, 270):
        raise APIError('Rotation must be 0, 90, 180 or 270.')
    for key, default, low, high in [('background_angle', 90, 0, 360), ('zoom', 1, 1, 4), ('x', .5, 0, 1), ('y', .5, 0, 1),
                                  ('brightness', converter.PROFILES[out['profile']]['brightness'], 0, 2),
                                  ('contrast', converter.PROFILES[out['profile']]['contrast'], 0, 2),
                                  ('saturation', converter.PROFILES[out['profile']]['saturation'], 0, 2)]:
        value = data.get(key, default)
        if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
            raise APIError(f'Invalid {key} (expected {low}–{high}).')
        out[key] = value
    return out


def compose_image(image, frame, settings):
    """Fit in display coordinates; the browser uses exactly the same crop formula."""
    panel = converter.PANELS[frame['screen']]
    orientation = frame['orientation']
    colors = gradient_colors(image)
    image = image.rotate(-settings['rotation'], expand=True)
    width, height = (panel.width, panel.height) if orientation == 'portrait' else (panel.height, panel.width)
    if settings['fit'] == 'crop':
        crop_w = min(image.width, image.height * width / height) / settings['zoom']
        crop_h = crop_w * height / width
        left = (image.width - crop_w) * settings['x']
        top = (image.height - crop_h) * settings['y']
        picture = image.resize((width, height), Image.Resampling.LANCZOS,
                               box=(left, top, min(image.width, left + crop_w), min(image.height, top + crop_h)))
    else:
        picture = converter.scale_to_frame(image, 'letterbox', panel, orientation)
    picture = converter.enhance_subject(picture, settings['brightness'], settings['contrast'], settings['saturation'], settings['profile'])
    picture = extend_to_frame(picture, (width, height), settings['fit'] == 'letterbox')
    picture = flatten(picture, settings.get('background', 'solid'), settings.get('background_color', '#ffffff'), settings.get('background_angle', 90), colors)
    return picture


def convert_job(source_path, directory, frame, settings):
    """Spawn-safe worker, shared palette/packing with the CLI; returns real BIN preview."""
    with Image.open(source_path) as source:
        image = compose_image(source.convert('RGBA'), frame, settings)
    if frame['orientation'] == 'landscape':
        image = image.transpose(Image.Transpose.ROTATE_270)
    indices = converter.quantize_image(image, settings['dither'])
    target = Path(directory) / 'image.bin'
    converter.generate_binary_file(indices, target, converter.PANELS[frame['screen']])
    preview, _ = decode(target)
    if frame['orientation'] == 'landscape':
        preview = preview.transpose(Image.Transpose.ROTATE_90)
    preview.save(Path(directory) / 'preview.png')
    return target.stat().st_size


class Studio:
    def __init__(self, config_path, app_name=DEFAULT_APP_NAME):
        self.app_name = app_name
        self.config_path = Path(config_path)
        self.config = validate_frames(json.loads(self.config_path.read_text())) if self.config_path.exists() else {'version': 1, 'frames': []}
        self.temp = tempfile.TemporaryDirectory(prefix='fraimic-studio-')
        self.root = Path(self.temp.name)
        self.token = secrets.token_urlsafe(32)
        self.lock = RLock()
        self.sources, self.jobs = {}, {}
        self.processes = ProcessPoolExecutor(max_workers=1, mp_context=get_context('spawn'))
        self.transfers = ThreadPoolExecutor(max_workers=1)

    def close(self):
        self.processes.shutdown(wait=True)
        self.transfers.shutdown(wait=True)
        self.temp.cleanup()

    def save_config(self, data):
        config = validate_frames(data)
        with self.lock:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replace prevents partial JSON if interrupted during saving.
            with tempfile.NamedTemporaryFile('w', dir=self.config_path.parent, prefix='.frames-', suffix='.json', delete=False) as f:
                temporary = Path(f.name)
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.write('\n')
            try:
                temporary.replace(self.config_path)
            finally:
                temporary.unlink(missing_ok=True)
            self.config = config
        return config

    def frame(self, key):
        for frame in self.config['frames']:
            if frame['id'] == key:
                return dict(frame)
        raise APIError('Select a saved frame first.')

    def add_image(self, raw, name):
        suffix = Path(name).suffix.lower()
        if suffix not in ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'):
            raise APIError('Choose a JPG, PNG, WebP or HEIC image.')
        if suffix in ('.heic', '.heif') and not converter.HEIC_SUPPORTED:
            raise APIError('HEIC support requires pillow-heif. Install it in your Python environment.')
        import io
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise APIError('Image too large (maximum 40 megapixels).')
                source = ImageOps.exif_transpose(source)
                image = source.convert('RGBA')
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise APIError(f'Unable to read this image: {exc}')
        key = uuid.uuid4().hex
        directory = self.root / key
        directory.mkdir()
        image.save(directory / 'source.png')
        transparent = has_transparency(image)
        colors = gradient_colors(image)
        width, height = image.size
        image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        image.save(directory / 'source-preview.png')
        info = dict(transparent=transparent, background_colors=colors, id=key, name=Path(name).name, width=width, height=height,
                    url=f'/media/{key}/source-preview.png')
        with self.lock:
            self.sources[key] = info
        return info

    def start_conversion(self, data):
        with self.lock:
            if any(j['status'] == 'converting' for j in self.jobs.values()):
                raise APIError('A conversion is already running. Please wait.', 409)
            frame = self.frame(data.get('frame_id'))
            source_id = data.get('source_id')
            if source_id not in self.sources:
                raise APIError('Choose an image first.')
            settings = validate_settings(data.get('settings'))
            key = uuid.uuid4().hex
            directory = self.root / key
            directory.mkdir()
            job = dict(id=key, status='converting', frame=frame, settings=settings,
                       source_id=source_id, message='Converting image…')
            self.jobs[key] = job
            future = self.processes.submit(convert_job, str(self.root / source_id / 'source.png'), str(directory), frame, settings)
            future.add_done_callback(lambda done: self.converted(key, done))
            return dict(job)

    def converted(self, key, future):
        with self.lock:
            try:
                size = future.result()
                self.jobs[key].update(status='ready', bytes=size, preview=f'/media/{key}/preview.png',
                                      bin=f'/media/{key}/image.bin', message='Conversion ready. Check the preview before sending.')
            except Exception as exc:
                self.jobs[key].update(status='error', message=f'Conversion failed: {exc}')

    def start_upload(self, data):
        with self.lock:
            job = self.jobs.get(data.get('job_id'))
            if not job or job['status'] not in ('ready', 'sent', 'upload_error'):
                raise APIError('Convert the image before sending it.', 409)
            if self.frame(data.get('frame_id')) != job['frame']:
                raise APIError('The frame configuration changed. Convert again before sending.', 409)
            if any(j['status'] == 'sending' for j in self.jobs.values()):
                raise APIError('An upload is already running.', 409)
            job.update(status='sending', message='Sending to the frame…', battery=None)
            self.transfers.submit(self.transfer, job['id'])
            return dict(job)

    def transfer(self, key):
        frame = self.jobs[key]['frame']
        battery = None
        try:
            status, body = upload_bin(frame['host'], self.root / key / 'image.bin', screen=frame['screen'])
            if not 200 <= status < 300:
                raise ValueError(f'HTTP {status}: {body}')
            try:
                reply = json.loads(body)
            except ValueError:
                reply = {}
            if isinstance(reply, dict) and (reply.get('error') or reply.get('success') is False or reply.get('status') in ('error', 'failed')):
                raise ValueError(str(reply))
            message = f'Image accepted by {frame["name"]} (HTTP {status}). The frame may still be rendering.'
            battery = read_battery(frame['host'])
            message += ' ' + battery_message(battery)
            state = 'sent'
        except urllib.error.HTTPError as exc:
            with exc:
                detail = exc.read(4096).decode('utf-8', 'replace')
            state, message = 'upload_error', f'Frame rejected the image: HTTP {exc.code}. {detail}'
        except Exception as exc:
            state, message = 'upload_error', f'Upload failed. Check that the frame is awake and on this network. {exc}'
        with self.lock:
            self.jobs[key].update(status=state, message=message, battery=battery)


class Handler(BaseHTTPRequestHandler):
    server_version = 'FraimicLocal/1.0'

    @property
    def studio(self):
        return self.server.studio

    def log_message(self, format, *args):
        pass

    def reply(self, data, status=200, content_type='application/json'):
        if content_type == 'application/json':
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def check_request(self, write=False):
        expected = f'127.0.0.1:{self.server.server_port}'
        allowed = {expected: 'http://' + expected}
        public_origin = getattr(self.server, 'public_origin', None)
        if public_origin:
            allowed[urlsplit(public_origin).netloc] = public_origin
        host = self.headers.get('Host')
        if host not in allowed:
            raise APIError('Invalid host.', 403)
        origin = self.headers.get('Origin')
        if origin and origin != allowed[host]:
            raise APIError('Cross-origin request rejected.', 403)
        if write and not secrets.compare_digest(self.headers.get('X-Studio-Token', ''), self.studio.token):
            raise APIError('Session expired. Reload the page.', 403)

    def do_GET(self):
        try:
            self.check_request()
            path = urlsplit(self.path).path
            if path == '/api/state':
                with self.studio.lock:
                    return self.reply(dict(config=self.studio.config, token=self.studio.token,
                                           dithers=converter.dither_options(), default_dither=converter.DEFAULT_DITHER, heic=converter.HEIC_SUPPORTED, profiles=converter.PROFILES, default_profile=converter.DEFAULT_PROFILE, config_path=str(self.studio.config_path)))
            if path.startswith('/api/jobs/'):
                with self.studio.lock:
                    job = self.studio.jobs.get(path.rsplit('/', 1)[-1])
                    if job is None:
                        raise APIError('Unknown conversion.', 404)
                    return self.reply(job)
            static = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/icon.png': ('icon.png', 'image/png'),
                      '/favicon.ico': ('favicon.ico', 'image/x-icon'),
                      '/apple-touch-icon.png': ('apple-touch-icon.png', 'image/png'),
                      '/icon.svg': ('icon.svg', 'image/svg+xml')}
            if path in static:
                filename, mime = static[path]
                content = (ROOT / 'web' / filename).read_bytes()
                if filename == 'index.html':
                    content = content.decode('utf-8').replace('{{APP_NAME}}', escape(self.studio.app_name)).encode('utf-8')
                return self.reply(content, content_type=mime)
            match = re.fullmatch(r'/media/([a-f0-9]{32})/(source-preview\.png|preview\.png|image\.bin)', path)
            if match:
                file = self.studio.root / match[1] / match[2]
                if file.is_file():
                    mime = 'image/png' if file.suffix == '.png' else 'application/octet-stream'
                    return self.reply(file.read_bytes(), content_type=mime)
            raise APIError('Not found.', 404)
        except APIError as exc:
            self.reply({'error': str(exc)}, exc.status)
        except OSError as exc:
            self.reply({'error': str(exc)}, 500)

    def do_POST(self):
        try:
            self.check_request(write=True)
            path = urlsplit(self.path).path
            limit = MAX_UPLOAD if path == '/api/images' else 65536
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise APIError('Invalid request size.')
            if not 0 < size <= limit:
                raise APIError('File or request too large (image limit: 60 MB).', 413)
            raw = self.rfile.read(size)
            if path == '/api/images':
                result = self.studio.add_image(raw, unquote(self.headers.get('X-Filename', 'image')))
            else:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise APIError('Expected a JSON object.')
                if path == '/api/config':
                    result = self.studio.save_config(data)
                elif path == '/api/convert':
                    result = self.studio.start_conversion(data)
                elif path == '/api/send':
                    result = self.studio.start_upload(data)
                else:
                    raise APIError('Not found.', 404)
            self.reply(result)
        except APIError as exc:
            self.reply({'error': str(exc)}, exc.status)
        except (ValueError, TypeError, OSError) as exc:
            self.reply({'error': str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser(description='Open the local, single-page Fraimic editor.')
    parser.add_argument('-c', '--config', type=Path, default=ROOT / 'frames.json', help='Frame JSON file (default: frames.json beside this script)')
    parser.add_argument('-p', '--port', type=int, default=0, help='Local port (default: choose a free port)')
    parser.add_argument('-n', '--no-browser', action='store_true', help='Print the URL without opening a browser')
    parser.add_argument('-b', '--bind', default='127.0.0.1', help='Listen address (default: 127.0.0.1; use 0.0.0.0 for Docker/LAN)')
    parser.add_argument('-u', '--public-origin', default=os.environ.get('FRAIMIC_PUBLIC_ORIGIN'), help='Exact browser origin for LAN access, e.g. http://tower:8080 (or FRAIMIC_PUBLIC_ORIGIN)')
    args = parser.parse_args()
    if args.bind != '127.0.0.1' and not args.public_origin:
        parser.error('--public-origin is required when listening outside 127.0.0.1')
    if args.public_origin:
        try:
            validate_origin(args.public_origin)
        except ValueError as exc:
            parser.error(str(exc))
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    studio = None
    try:
        studio = Studio(args.config.resolve(), app_name=load_app_name())
        with ThreadingHTTPServer((args.bind, args.port), Handler) as server:
            server.studio = studio
            server.public_origin = args.public_origin
            url = args.public_origin or f'http://127.0.0.1:{server.server_port}'
            print(f'{studio.app_name}: {url}\nFrames: {studio.config_path}\nTemporary files: {studio.root}\nPress Ctrl+C to stop and remove temporary images.', flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        print(f'\nClosing {studio.app_name if studio else DEFAULT_APP_NAME}…')
    except (OSError, ValueError, APIError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    finally:
        if studio:
            studio.close()


if __name__ == '__main__':
    main()
