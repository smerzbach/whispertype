#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Resolve venv path — priority order:
#   1. WHISPERTYPE_VENV env var (set by install.sh)
#   2. venv_path key in config.ini
#   3. venv_path key in config.ini.example
# ---------------------------------------------------------------------------
if [ -n "${WHISPERTYPE_VENV:-}" ]; then
    VENV_PATH="$WHISPERTYPE_VENV"
else
    if [ -f "$SCRIPT_DIR/config.ini" ]; then
        INI_SOURCE="$SCRIPT_DIR/config.ini"
    elif [ -f "$SCRIPT_DIR/config.ini.example" ]; then
        INI_SOURCE="$SCRIPT_DIR/config.ini.example"
    else
        echo "Error: config.ini.example not found and WHISPERTYPE_VENV is not set."
        read -rp "Press Enter to exit" _
        exit 1
    fi
    VENV_PATH="$(grep "^venv_path" "$INI_SOURCE" | cut -d= -f2 | tr -d ' ' | envsubst)"
    if [ -z "$VENV_PATH" ]; then
        echo "Error: Could not read venv_path from $INI_SOURCE and WHISPERTYPE_VENV is not set."
        read -rp "Press Enter to exit" _
        exit 1
    fi
fi

# Expand ~ / env vars that weren't caught by envsubst (e.g. literal $HOME)
VENV_PATH="$(eval echo "$VENV_PATH")"

# ---------------------------------------------------------------------------
# Create venv + install deps if it doesn't exist yet
# (covers the case where start-whispertype.sh is called directly without
#  running install.sh first)
# ---------------------------------------------------------------------------
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment at $VENV_PATH ..."
    python3 -m venv "$VENV_PATH"
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate"

    if command -v dpkg &>/dev/null && ! dpkg -l python3-gi &>/dev/null 2>&1; then
        echo "Installing required system packages (python3-gi)..."
        sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0
    fi

    pip install -r "${SCRIPT_DIR}/requirements.txt"
else
    # shellcheck disable=SC1091
    source "$VENV_PATH/bin/activate"
fi

# ---------------------------------------------------------------------------
# Launch WhisperType
# ---------------------------------------------------------------------------
CLIENT_PATH="${SCRIPT_DIR}/whispertype.py"

if [ -f "${SCRIPT_DIR}/clean_python.sh" ]; then
    "${SCRIPT_DIR}/clean_python.sh" python3 "$CLIENT_PATH"
else
    python3 "$CLIENT_PATH"
fi

read -rp "Press Enter to quit" _
