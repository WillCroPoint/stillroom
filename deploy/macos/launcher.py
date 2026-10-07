"""Optional native shell; the server and editor remain shared with Docker."""
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
    return Path(os.environ.get('STILLROOM_DATA_DIR',
        str(Path.home() / 'Library/Application Support/Stillroom'))).expanduser()


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
    from mac_branding import window_name
    from gui import Handler, Studio

    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        name = window_name(directory)
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
        webview.start()
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
        from AppKit import NSAlert, NSApplication
        application = NSApplication.sharedApplication()
        application.setActivationPolicy_(0)
        application.finishLaunching()
        application.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_('Stillroom could not start')
        alert.setInformativeText_(f'{exc}\n\nDetails (if writable):\n{log_path}')
        alert.addButtonWithTitle_('OK')
        alert.runModal()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
