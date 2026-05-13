@echo off
REM Launch SkywardRaceLAN with --dev so it uses the DevProfile1-DevProfile5 slots.
REM Lives next to SkywardRaceLAN.exe; copied into dist\SkywardRaceLAN\ by build_exe.ps1.
start "" "%~dp0SkywardRaceLAN.exe" --dev
