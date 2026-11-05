@echo off
rem Starts NULLROUTE on Windows.
rem The first run creates a Python virtual environment in .venv and installs
rem Textual into it; later runs start straight away.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Setting up the Python environment, one moment...
    python -m venv .venv || py -3 -m venv .venv || goto :error
)
.venv\Scripts\python -c "import textual" >nul 2>&1 || (
    echo Installing Textual...
    .venv\Scripts\python -m pip install --quiet "textual>=1.0" || goto :error
)
.venv\Scripts\python -m nullroute %*
goto :eof

:error
echo Could not set up Python. Install Python 3.10+ from python.org (tick "Add to PATH") and try again.
pause
