"""Optional Windows shell; the server and editor remain shared with Docker."""
import multiprocessing

# Must precede GUI imports: frozen conversion workers re-enter this executable.
if __name__ == '__main__':
    multiprocessing.freeze_support()

import os
from pathlib import Path
import sys
from threading import Thread
from http.server import ThreadingHTTPServer

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def data_directory():
    override = os.environ.get('STILLROOM_DATA_DIR')
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get('APPDATA')
    base = Path(appdata) if appdata else Path.home() / 'AppData/Roaming'
    return (base / 'Stillroom').expanduser()


def confirm_active_work(studio, window):
    with studio.lock:
        busy = any(job['status'] in ('converting', 'sending')
                   for job in studio.jobs.values())
    if not busy:
        return True
    return window.create_confirmation_dialog(
        'Work in progress',
        'A conversion or transfer is still running. Close the window? '
        'The current operation will finish before the application quits.')


def run():
    import webview
    from branding import load_app_name
    from gui import Handler, Studio

    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        name = load_app_name(directory / 'branding.local.json')
        studio = Studio(directory / 'frames.json', app_name=name)
    except (OSError, ValueError) as exc:
        raise ValueError(f'Could not load settings in {directory}: {exc}') from exc
    server = None
    thread = None
    try:
        # Port zero asks the OS to reserve an available port atomically.
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.studio = studio
        server.public_origin = None
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        window = webview.create_window(name, f'http://127.0.0.1:{server.server_port}',
            width=1280, height=900, min_size=(640, 560),
            background_color='#fff8ef')
        window.events.closing += lambda: confirm_active_work(studio, window)
        webview.start(gui='edgechromium')
    finally:
        if thread:
            server.shutdown()
            thread.join()
        if server:
            server.server_close()
        studio.close()


def main():
    log_path = data_directory() / 'launcher.log'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # One startup per log; keep the previous session for diagnosis.
        if log_path.exists():
            log_path.replace(log_path.with_suffix('.previous.log'))
        with log_path.open('w', buffering=1) as log:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            try:
                run()
            except Exception:
                import traceback
                traceback.print_exc()
                raise
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
    except Exception as exc:
        # Native alert also works when the web server never started.
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f'{exc}\n\nDetails (if writable):\n{log_path}\n\n'
            'If the web engine could not start, install Microsoft Edge WebView2 Runtime.',
            'Stillroom could not start', 0x10)
        return 1
    return 0


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from smoke_test import run_check
        sys.exit(run_check(Path(sys.argv[2])))
    sys.exit(main())
