@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM  Expedition Manager launcher (Windows)
REM  Creates the venv if missing, installs the dependencies,
REM  and re-runs the program inside the venv.
REM ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo Error: Python was not found on the system PATH.
    echo Install it from https://www.python.org (check "Add python to PATH").
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo Error: could not create the venv.
        exit /b 1
    )
)

powershell -NoProfile -Command "if (-not (Test-Path .venv\.deps_hash) -or ((Get-Content .venv\.deps_hash -Raw).Trim() -ne (Get-FileHash requirements.txt -Algorithm MD5).Hash)) { exit 1 }"
if errorlevel 1 (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    powershell -NoProfile -Command "(Get-FileHash requirements.txt -Algorithm MD5).Hash" > .venv\.deps_hash
)

REM GUI backend check: make sure a Qt6 binding (PyQt6/PySide6) is
REM importable. On Windows the venv is isolated, so if neither is
REM available we install PySide6 (LGPL, wheels for all platforms).
if /i "%~1"=="gui" (
    ".venv\Scripts\python.exe" -c "import PyQt6" >nul 2>nul
    if errorlevel 1 (
    ".venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
        if errorlevel 1 (
            echo No Qt6 binding found. Installing PySide6 into the venv...
            ".venv\Scripts\python.exe" -m pip install --quiet PySide6
        )
    )
)

".venv\Scripts\python.exe" run.py %*
exit /b %errorlevel%
