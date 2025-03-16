#!/bin/bash

# Create applications directory if it doesn't exist
mkdir -p ~/.local/share/applications/

# Get the absolute path of the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create a temporary copy of the desktop file
cp "${SCRIPT_DIR}/whispertype.desktop" /tmp/whispertype.desktop.tmp

# Replace the Exec line with absolute path
sed -i "s|^Exec=\./start-whispertype\.sh|Exec=${SCRIPT_DIR}/start-whispertype.sh|" /tmp/whispertype.desktop.tmp

# Install the modified desktop file
mv /tmp/whispertype.desktop.tmp ~/.local/share/applications/whispertype.desktop

# Make the desktop file executable
chmod +x ~/.local/share/applications/whispertype.desktop

echo "WhisperType desktop entry has been installed to ~/.local/share/applications/" 