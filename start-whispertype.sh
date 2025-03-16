#!/bin/bash

# Get the absolute path of the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure config.ini exists
if [ ! -f "$SCRIPT_DIR/config.ini" ]; then
    if [ -f "$SCRIPT_DIR/config.ini.example" ]; then
        cp "$SCRIPT_DIR/config.ini.example" "$SCRIPT_DIR/config.ini"
        echo "Created config.ini from example file"
    else
        echo "Error: config.ini.example not found"
        read -p "Press Enter to exit"
        exit 1
    fi
fi

# Read venv path from ini file and expand environment variables
WHISPER_VENV_PATH=$(grep "^venv_path" "$SCRIPT_DIR/config.ini" | cut -d= -f2 | tr -d ' ' | envsubst)

# Verify we got a value
if [ -z "$WHISPER_VENV_PATH" ]; then
    echo "Error: Could not read venv_path from config.ini"
    read -p "Press Enter to exit"
    exit 1
fi

# Path to the whisper client script
CLIENT_PATH="${SCRIPT_DIR}/whispertype.py"

# Create virtual environment if it doesn't exist
if [ ! -d "$WHISPER_VENV_PATH" ]; then
    echo "Creating virtual environment at $WHISPER_VENV_PATH"
    python3 -m venv "$WHISPER_VENV_PATH"
    source "$WHISPER_VENV_PATH/bin/activate"
    
    # Install system dependencies if needed
    if ! dpkg -l | grep -q "python3-gi"; then
        echo "Installing required system packages..."
        sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0
    fi
    
    pip install -r "${SCRIPT_DIR}/requirements.txt"
else
    # Activate virtual environment
    source "$WHISPER_VENV_PATH/bin/activate"
fi

# Run the client
if [ -f "${SCRIPT_DIR}/clean_python.sh" ]; then
    "${SCRIPT_DIR}/clean_python.sh" python3 "$CLIENT_PATH"
else
    python3 "$CLIENT_PATH"
fi 


read -p "Press Enter to quit"