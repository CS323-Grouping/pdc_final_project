# Build Windows executable (onedir) using PyInstaller + TowerJumpLAN.spec
# Bump semver/build before shipping: edit app/version.py (BUILD_NUMBER, VERSION_*).
# Prerequisites: pip install -r requirements-dev.txt
# Ship the entire dist\TowerJumpLAN\ folder (exe + _internal + DLLs), not only the .exe.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m PyInstaller --noconfirm --clean TowerJumpLAN.spec

$distDir = Join-Path $root "dist\TowerJumpLAN"
Copy-Item -Path (Join-Path $PSScriptRoot "dev.bat") -Destination (Join-Path $distDir "dev.bat") -Force

Write-Host "Output: $distDir\TowerJumpLAN.exe"
Write-Host "Dev launcher: $distDir\dev.bat"
