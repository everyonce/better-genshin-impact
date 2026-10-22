@echo off
setlocal
set "BETTERGI_DIR=%~dp0artifacts\BetterGI-English-win-x64"
if not exist "%BETTERGI_DIR%\BetterGI.exe" (
    echo The local build is missing. Run this command in PowerShell 7:
    echo   .\Build\Scripts\build-local.ps1
    exit /b 1
)
start "" /D "%BETTERGI_DIR%" "%BETTERGI_DIR%\BetterGI.exe"
