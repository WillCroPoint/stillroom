#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
    echo 'Build this bundle on macOS.' >&2
    exit 1
fi
"${PYTHON:-python3}" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export PYINSTALLER_CONFIG_DIR="$PWD/build/cache"
.venv/bin/python -m PyInstaller --noconfirm --clean --distpath dist --workpath build Stillroom.spec
echo "Build complete. Applications are in: $PWD/dist"
