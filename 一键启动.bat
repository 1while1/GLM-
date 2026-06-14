@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating virtual environment...
  python -m venv .venv
)

echo [INFO] Installing/updating dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

set PLAYWRIGHT_BROWSERS_PATH=%CD%\.ms-playwright
if not exist ".ms-playwright\chromium-1223" (
  echo [INFO] Installing Chromium into project directory...
  ".venv\Scripts\python.exe" -m playwright install chromium
)

set PYTHONPATH=%CD%\src
start "GLM Coding Plan Grabber" ".venv\Scripts\pythonw.exe" "%CD%\gui.py"
