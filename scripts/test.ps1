# Runs the Godot client's GUT test suite headless.
# Usage:  pwsh scripts/test.ps1
# Returns a non-zero exit code if any test fails (CI-friendly via -gexit).

$ErrorActionPreference = "Stop"

$godot = "C:\Program Files (x86)\Godot\Godot_v4.6.2-stable_win64_console.exe"
$proj = Join-Path $PSScriptRoot "..\godot"

if (-not (Test-Path $godot)) {
	Write-Error "Godot not found at $godot - update the path in scripts/test.ps1"
	exit 1
}

& $godot --headless --path $proj `
	-s addons/gut/gut_cmdln.gd `
	-gdir=res://tests `
	-ginclude_subdirs `
	-gexit

exit $LASTEXITCODE
