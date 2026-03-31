@echo off
:: Launches WhisperType inside the correct Python venv.
:: Venv resolution order:
::   1. WHISPERTYPE_VENV env var (set by install.bat)
::   2. venv_path key in config.ini
::   3. venv_path key in config.ini.example
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "SCRIPT_DIR=%~dp0"
:: Remove trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: -----------------------------------------------------------------------
:: Resolve venv path
:: -----------------------------------------------------------------------
if defined WHISPERTYPE_VENV (
    set "VENV_PATH=%WHISPERTYPE_VENV%"
    goto :venv_resolved
)

set "INI_SOURCE="
if exist "%SCRIPT_DIR%\config.ini" (
    set "INI_SOURCE=%SCRIPT_DIR%\config.ini"
) else if exist "%SCRIPT_DIR%\config.ini.example" (
    set "INI_SOURCE=%SCRIPT_DIR%\config.ini.example"
) else (
    echo Error: config.ini.example not found and WHISPERTYPE_VENV is not set.
    pause
    exit /b 1
)

for /f "tokens=2 delims== " %%A in ('findstr /b "venv_path" "%INI_SOURCE%"') do (
    set "VENV_PATH=%%A"
)

:: Expand %LOCALAPPDATA%, %USERPROFILE%, etc.
call set "VENV_PATH=%VENV_PATH%"

if not defined VENV_PATH (
    echo Error: Could not read venv_path from %INI_SOURCE%.
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
