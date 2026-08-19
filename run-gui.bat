@echo off
REM Expedition Manager - GUI launcher (Windows).
REM Thin wrapper over run.bat: reuses the venv bootstrap and adds the
REM "gui" subcommand.
cd /d "%~dp0"
call run.bat gui
exit /b %errorlevel%
