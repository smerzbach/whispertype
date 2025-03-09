#!/bin/bash

# Path to the virtual environment (can be overridden by environment variable)
VENV_PATH="${WHISPER_VENV_PATH:-$HOME/.venvs/whispertype}"

# Path to the whisper client script
CLIENT_PATH="$(dirname "$(readlink -f "$0")")/whispertype.py"

# Activate virtual environment and run the client
source "$VENV_PATH/bin/activate"
./clean_python.sh python3 "$CLIENT_PATH" 
