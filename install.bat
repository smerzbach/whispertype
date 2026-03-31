@echo off
:: Usage: install.bat [VENV_PATH]
::   VENV_PATH  Where to create the Python venv
::              (default: %LOCALAPPDATA%\whispertype\venv)
setlocal enabledelayedexpansion
cd /d "%~dp0"

if "%~1"=="" (
    set "VENV_PATH=%LOCALAPPDATA%\whispertype\venv"
) else (
    set "VENV_PATH=%~1"
)

echo === WhisperType installer ===
echo Venv: %VENV_PATH%

if not exist "%VENV_PATH%" (
    echo Creating virtual environment...
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo Python not found. Install Python 3 and ensure "python" is on PATH.
        pause
        exit /b 1
    )
)

call "%VENV_PATH%\Scripts\activate.bat"
python -m pip install -U pip --quiet
pip install -r "%~dp0requirements.txt"

echo.
echo Dependencies installed.
echo Launching WhisperType setup...
echo.

:: Pass the venv path to start-whispertype.bat via env var.
set "WHISPERTYPE_VENV=%VENV_PATH%"
call "%~dp0start-whispertype.bat"
endlocal
