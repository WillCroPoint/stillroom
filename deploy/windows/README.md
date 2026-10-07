# Windows application

Docker/Unraid and Linux servers remain the primary deployment. This
Windows wrapper reuses the same editor and converter. Its packaging and launcher
live here; the server does not depend on Windows-specific libraries.

## Download and run

Download `Stillroom-windows-x64.zip` from the
[GitHub Releases page](https://github.com/WillCroPoint/stillroom/releases).
Extract it once, keep the entire **Stillroom** folder together, and open
**Stillroom.exe**. The automatically generated **Source code** archives are not
application packages.

### Development builds from Actions

In the GitHub repository, open **Actions → Windows application**, select a
successful run, then download **Stillroom-windows-x64** from **Artifacts**.
GitHub may require you to sign in. Artifacts expire after seven days.

Extract the downloaded artifact, then extract `Stillroom-windows-x64.zip`.
Keep the entire **Stillroom** directory together (including `_internal`), and
open **Stillroom.exe**. Moving only the EXE will break the application.
Python and the conversion dependencies are included; Docker is not required.

The downloaded package has been tested on **Windows 10 64-bit (x64)**. Windows 11 x64
will be listed as tested only after a separate validation. The interface needs Microsoft's
[WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)
and .NET Framework 4.6.2 or newer. Verify these prerequisites on the test PC;
if WebView2 is missing, install its Evergreen Runtime from
Microsoft. The app reports startup errors in a Windows dialog instead of silently
falling back to Internet Explorer. No runtime is silently downloaded or installed.

The application is not code-signed. Windows SmartScreen may warn about an unknown
publisher. Only run builds obtained from this repository that you trust; managed
PCs may prevent this. Never disable antivirus or global Windows protections.

## Settings and personal branding

Application preferences are ordinary JSON files, **not registry entries**:

```text
%APPDATA%\Stillroom\frames.json
%APPDATA%\Stillroom\branding.local.json
```

Paste `%APPDATA%\Stillroom` into Explorer's address bar to open the folder.
The first launch starts with no frames. Add them in the editor, or copy an existing
`frames.json` here while the app is closed. For a custom window and editor title:

```json
{"app_name": "Fraimic Studio"}
```

`STUDIO_APP_NAME` overrides the JSON value if set. The EXE filename remains
Stillroom. Configuration is never included in downloadable builds. Photos and
conversion results are temporary; save the BIN before quitting to retain it.
`launcher.log` and `launcher.previous.log` in the same folder contain diagnostics.
Review these files for private information before sharing them.

The server listens only on `127.0.0.1`, using a port reserved automatically by
Windows. Closing an idle window quits immediately. During conversion or transfer,
a confirmation explains that pending work will finish before the app exits.
The frame must be awake and reachable on the same network to receive an image.

## Build locally

Install Python 3.13 **x64**, including pip, then obtain a copy of the repository.
In PowerShell, from the repository root:

```powershell
./deploy/windows/build.ps1
```

If Python is not on PATH, pass `-Python 'C:\path\to\python.exe'`.
Use your organization's approved PowerShell policy if scripts are restricted.
The script installs dependencies into `deploy/windows/.venv` and writes the
portable folder and ZIP under `deploy/windows/dist`. No Visual Studio installation
is expected when the dependencies have precompiled wheels. Build on Windows;
PyInstaller does not produce a Windows executable from macOS.

For isolated development, `STILLROOM_DATA_DIR` overrides the settings directory.
The optional external `epd-dither` executable is not included.

## GitHub Actions

The [workflow](../../.github/workflows/windows-build.yml) builds on a standard
Windows x64 runner using Python 3.13. It runs on relevant pushes, and supports
manual **Run workflow** once the workflow exists on the default branch. Forks
may need Actions enabled first. The workflow has read-only repository permissions
and does not publish releases or push commits. Short artifact retention avoids
accumulating old builds.

It tests the shared application (excluding Unix deployment tests), then runs a
conversion inside the packaged EXE. The frozen test checks bundled web resources
and the spawned conversion worker; it never sends an image to a physical frame.
A successful build is not a substitute for testing the actual Windows UI:
file selection, crop/rotation, preview, BIN export, frame upload, restart with
saved settings, and closing during a conversion or transfer.

## Validation status

The Windows build passed 51 application tests and a conversion check inside the
packaged executable on GitHub Actions. The maintainer then tested the downloaded
package on Windows 10 x64 and confirmed the complete workflow, including sending
an image to a physical frame and saved settings. No security warning appeared on
that PC; other installations may display SmartScreen warnings. Windows 11 remains
untested. Validate future packages on the advertised Windows versions; a successful
build on Windows Server alone does not establish desktop compatibility.
