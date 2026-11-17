@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 run_questcut.py %*
) else (
  python run_questcut.py %*
)
if errorlevel 1 (
  echo.
  echo Something went wrong. If Python is missing, install it from https://www.python.org/downloads/
  echo ^(tick "Add python.exe to PATH" during installation^) and double-click this file again.
  pause
)
