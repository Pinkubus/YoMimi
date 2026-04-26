@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

pip show PySide6 >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies ^(first run may take a while for ML model downloads^)...
    pip install -r requirements.txt
)

python run.py
