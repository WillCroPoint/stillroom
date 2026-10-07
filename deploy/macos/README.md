# macOS application

Docker/Unraid and Linux servers remain the primary deployment. This directory
adds a native window around the existing editor, without changing the server or
requiring Docker on a Mac. Python, the converter and the web assets are bundled.

## First launch of a downloaded app

Stillroom is not signed with an Apple Developer ID or notarized by Apple. macOS
will normally block the first launch of a copy downloaded from GitHub. This does
not mean you need Python or Docker: the application contains its dependencies.

When a macOS bundle is attached to a release:

1. Download the archive matching your Mac from the official
   [Stillroom releases](https://github.com/WillCroPoint/stillroom/releases).
   The automatically generated **Source code** archives are not the application.
2. Extract the archive, move **Stillroom.app** to **Applications**, and double-click it.
3. If macOS says it cannot verify the developer or check the app for malicious
   software, it may offer only to close the app or move it to the Trash. Dismiss
   the warning, then open **System Settings → Privacy & Security**.
4. Scroll down to **Security**, find the message about Stillroom and click **Open Anyway**. Confirm with your
   password or Touch ID if requested, then confirm opening the application.
5. Subsequent launches normally work directly from Finder. A new download or an
   updated version may require approval again.

Only approve the copy you deliberately downloaded from this repository. No Terminal
command or global change to Gatekeeper is needed. If macOS reports detected malware
or a damaged app, stop and report the exact message rather than following this
exception procedure. Managed Macs may not allow this exception.

Apple provides an [illustrated explanation of these dialogs and the Open Anyway
button](https://support.apple.com/en-us/102445). Wording and layout vary with macOS
version and system language. A bundle built locally may not show these warnings.

## Build and open

On macOS, with Python 3.10 or newer installed:

```sh
./deploy/macos/build.sh
open deploy/macos/dist/Stillroom.app
```

To choose a Python installation, set `PYTHON=/path/to/python3` when running the
build script. Dependencies live in this directory's `.venv`; build outputs stay
in `build/` and `dist/`. All three are ignored by Git. The app targets the build
machine's architecture; an Apple Silicon build is not an Intel build. The oldest
supported macOS version also depends on the Python and binary dependencies used.

Public bundles are intended to remain
without Developer ID signing or notarization; include the first-launch instructions
above with each release. Test the downloaded archive on the advertised macOS
versions before publishing it. The build uses PyInstaller and pywebview's native WebKit window.
The optional `epd-dither` executable is not included.

## Build with a personal application name

The default public build is **Stillroom.app**. To change the Finder/Dock name,
macOS application menu and About panel, choose the name at build time:

```sh
MACOS_APP_NAME="Fraimic Studio" ./deploy/macos/build.sh
open "deploy/macos/dist/Fraimic Studio.app"
```

The editor and window use this name by default too. The bundle identifier and
settings directory stay unchanged, so renaming does not migrate or duplicate
frame settings. Treat differently named builds as alternatives, not independent
installations. Build names cannot contain `/` or `:`.

The build never reads your personal branding file or `STUDIO_APP_NAME`; only
`MACOS_APP_NAME` selects its identity. Omit it for the public Stillroom build.

## Settings and use

Frame settings are saved in:

```text
~/Library/Application Support/Stillroom/frames.json
```

The first launch starts with no frames. Add them in the editor, or, with the app
closed, copy an existing `frames.json` to that location. The app does not import
personal settings from the source checkout. Photos and conversion results are
temporary; save a BIN copy before quitting if you want to keep it.

For a personal display name, create `branding.local.json` in the same directory:

```json
{"app_name": "Fraimic Studio"}
```

This overrides the window and editor title after installation. Keep the existing
filename `branding.local.json` (not `branding.json`). Finder, the Dock and the macOS
menu retain the build-time name; changing those requires rebuilding. The settings
directory remains Stillroom. `STUDIO_APP_NAME` takes priority if set in the app's environment.
No personal branding, frames or photos are included in the build.

The local server listens only on `127.0.0.1`. macOS reserves a free port on each
launch, so there is no fixed port to configure. Closing an idle window quits immediately. During a conversion or transfer, a
confirmation explains that the current operation will finish before quitting.
Closing stops the server and removes temporary files after pending work completes. Frame uploads still require network access to
the frame; allow local network access if macOS asks.

## Troubleshooting and development

Startup failures display a native alert with the error and the log location.
`launcher.log` and `launcher.previous.log` in the settings directory contain the
current and previous launch diagnostics. Review logs before sharing them.

Run without rebuilding using:

```sh
deploy/macos/.venv/bin/python deploy/macos/launcher.py
```

For isolated development settings, set `STILLROOM_DATA_DIR` to a disposable
absolute directory. This override also works when launching the bundled executable
from a terminal. The standard browser-based editor remains available through
`python gui.py`; macOS dependencies are not required for that mode.

## Validation

The Apple Silicon application was tested with Python 3.14: native file selection,
photo conversion in the frozen worker process, BIN export (960,000 bytes for
the 13.3-inch panel), server shutdown and a visible startup error for invalid
settings. The existing 53 tests also pass with the macOS build dependencies.
The maintainer also tested the downloaded public archive, approved its first
launch through Privacy & Security, and successfully sent an image to a physical
frame. Intel Macs and older macOS versions remain untested.

## Preparing release notes

Use [RELEASE_NOTES_TEMPLATE.md](RELEASE_NOTES_TEMPLATE.md) for the macOS section
of a GitHub release. Include a short first-launch reminder there and link to this
guide. Release descriptions support Markdown images: embed a genuine screenshot
of the Stillroom warning and the **Open Anyway** setting when captured from a
downloaded build. Keep images in `docs/images/` and use absolute GitHub image URLs
pinned to the release tag in release notes, so later documentation edits do not
change an older release. Avoid personal details in screenshots.
