@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment with Python 3.12...
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv. Install Python 3.12 first.
    exit /b 1
  )
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  echo Installing PyTorch CPU...
  .\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  echo Installing project requirements...
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo.
echo Starting WasteAI on http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.
.\.venv\Scripts\python.exe app.py
