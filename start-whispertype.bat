@echo off
:: Launches WhisperType inside the correct Python venv.
:: Venv resolution order:
::   1. WHISPERTYPE_VENV env var (set by install.bat)
::   2. venv_path key in config.ini
::   3. venv_path key in config.ini.example
::
:: Path values in the ini file (e.g. ${HOME}/...) are resolved by Python so
:: they expand correctly on all platforms.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "SCRIPT_DIR=%~dp0"
:: Remove trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: -----------------------------------------------------------------------
:: Resolve venv path
:: -----------------------------------------------------------------------
if defined WHISPERTYPE_VENV (
    set "VENV_PATH=!WHISPERTYPE_VENV!"
    goto :venv_resolved
)

:: Use Python helper to read and fully expand venv_path from the ini file.
:: This handles ${HOME}/..., %USERPROFILE%/..., and any other env syntax.
for /f "delims=" %%P in ('python "%SCRIPT_DIR%\get_venv_path.py"') do (
    set "VENV_PATH=%%P"
)

if not defined VENV_PATH (
    echo Error: Could not read venv_path from config.ini or config.ini.example.
    echo        Set WHISPERTYPE_VENV or add a venv_path entry to your config.
    pause
    exit /b 1
)

:venv_resolved
echo Venv: %VENV_PATH%

:: -----------------------------------------------------------------------
:: Create venv + install deps if missing
:: -----------------------------------------------------------------------
if not exist "%VENV_PATH%" (
    echo Creating virtual environment at %VENV_PATH% ...
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo Python not found. Install Python 3 and ensure "python" is on PATH.
        pause
        exit /b 1
    )
    call "%VENV_PATH%\Scripts\activate.bat"
    pip install -r "%SCRIPT_DIR%\requirements.txt"
) else (
    call "%VENV_PATH%\Scripts\activate.bat"
)

:: -----------------------------------------------------------------------
:: Launch WhisperType
:: -----------------------------------------------------------------------
python "%SCRIPT_DIR%\whispertype.py"

pause
endlocal
