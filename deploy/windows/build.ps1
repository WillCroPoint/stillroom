param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Build this package on Windows.' }
Push-Location $PSScriptRoot
try {
    & $Python -c "import platform, struct, sys; sys.exit(0 if platform.machine().lower() in ('amd64', 'x86_64') and struct.calcsize('P') == 8 else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Use an x64 Python installation for this x64 package.' }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
    $BuildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $BuildPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $BuildPython -m PyInstaller --noconfirm --clean --distpath dist --workpath build Stillroom.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    Copy-Item README.md dist\Stillroom\WINDOWS-README.md
    Compress-Archive -Path dist\Stillroom -DestinationPath dist\Stillroom-windows-x64.zip -Force
    Write-Host "Built: $PSScriptRoot\dist\Stillroom-windows-x64.zip"
} finally {
    Pop-Location
}
