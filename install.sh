#!/usr/bin/env bash
# Usage: install.sh [VENV_PATH]
#   VENV_PATH  Where to create the Python venv (default: ~/.venvs/whispertype)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV_PATH="${1:-${HOME}/.venvs/whispertype}"
VENV_PATH="$(eval echo "$VENV_PATH")"   # expand ~ if user typed it literally

echo "=== WhisperType installer ==="
echo "Venv: $VENV_PATH"

if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"
python -m pip install -U pip --quiet
pip install -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "Dependencies installed."
echo "Launching WhisperType setup..."
echo ""

# Pass the venv path to start-whispertype.sh via env var so it doesn't need
# a config.ini to exist yet.
export WHISPERTYPE_VENV="$VENV_PATH"
exec "${SCRIPT_DIR}/start-whispertype.sh"
