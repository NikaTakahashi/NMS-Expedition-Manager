@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM  Expedition Manager launcher (Windows)
REM  Creates the venv if missing, installs the dependencies,
REM  and re-runs the program inside the venv.
REM  On any error the window pauses so the message stays visible.
REM ============================================================

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Error: Python was not found on the system PATH.
    echo Install Python 3.10 or newer from https://www.python.org
    echo and tick "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Error: could not create the virtual environment.
        echo.
        pause
        exit /b 1
    )
)

powershell -NoProfile -Command "if (-not (Test-Path .venv\.deps_hash) -or ((Get-Content .venv\.deps_hash -Raw).Trim() -ne (Get-FileHash requirements.txt -Algorithm MD5).Hash)) { exit 1 }"
if errorlevel 1 (
    echo First run detected - installing dependencies. This can take a few minutes.
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Error: failed to install dependencies. Check your internet connection.
        echo.
        pause
        exit /b 1
    )
    powershell -NoProfile -Command "(Get-FileHash requirements.txt -Algorithm MD5).Hash" > .venv\.deps_hash
)

REM GUI backend check: make sure a Qt6 binding, PyQt6 or PySide6, is
REM importable. On Windows the venv is isolated, so if neither is
REM available we install PySide6 from PyPI.
if /i "%~1"=="gui" (
    ".venv\Scripts\python.exe" -c "import PyQt6" >nul 2>nul
    if errorlevel 1 (
        ".venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
        if errorlevel 1 (
            echo Installing PySide6 into the venv. This is a large download, a few minutes.
            ".venv\Scripts\python.exe" -m pip install PySide6
            if errorlevel 1 (
                echo.
                echo Error: failed to install PySide6. Check your internet connection.
                echo.
                pause
                exit /b 1
            )
        )
    )
)

echo Starting Expedition Manager...
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 (
    echo.
    echo ------------------------------------------------------------
    echo The program exited with an error. Read the messages above.
    echo ------------------------------------------------------------
    echo.
    pause
)
exit /b
