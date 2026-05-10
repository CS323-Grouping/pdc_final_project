@echo off
REM Launch TowerJumpLAN with --dev so it uses the DevProfile1-DevProfile5 slots.
REM Lives next to TowerJumpLAN.exe; copied into dist\TowerJumpLAN\ by build_exe.ps1.
start "" "%~dp0TowerJumpLAN.exe" --dev
