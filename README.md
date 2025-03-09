# WhisperType - Voice-to-Text System Tray Tool

A real-time speech-to-text transcription tool using whisper.cpp server. It lives in your system tray, ready to transcribe your voice with a global hotkey. Designed for XFCE desktop environment, WhisperType provides a seamless way to convert speech to text anywhere in your system.

## Features

- System tray integration with status indicators
- Real-time audio recording with visual feedback
- Automatic transcription using whisper.cpp server
- Auto-copy to clipboard and auto-type functionality: transcribed text can be typed into focused UI elements, or be copied to clipboard
- Server management (start/stop) from the tray menu
- Configurable model and language settings
- Translation support (foreign to English)
- Global keyboard shortcuts
- Configurable via `config.ini` file

## Configuration

The application uses a `config.ini` file for all configurable parameters. The file should be in the same directory as the script. Here's what you can configure:

```ini
[Server]
host = localhost          # Server hostname
port = 7777              # Server port
url = http://...         # Server URL (auto-generated)

[Models]
models_dir = ${WHISPER_MODELS_DIR:-${HOME}/.local/share/whisper-cpp/models}
default_model = ggml-tiny.en.bin

[Recording]
min_duration = 0.1       # Minimum recording duration in seconds
sample_rate = 16000      # Audio sample rate

[Defaults]
language = en           # Default language
auto_copy = false       # Auto-copy to clipboard
auto_type = false       # Auto-type text
show_audio_meter = false
translate = false       # Translation to English

[Server Command]
command = whisper-server ...  # Command to start the server
```

### Environment Variables

The application supports the following environment variables:
- `WHISPER_MODELS_DIR`: Path to the directory containing whisper.cpp model files (*.bin)
- `WHISPER_VENV_PATH`: Path to the Python virtual environment (default: `$HOME/.venvs/whispertype`)

### Default Paths

If not configured otherwise, the application uses these default paths:
- Models directory: `$HOME/.local/share/whisper-cpp/models`
- Virtual environment: `$HOME/.venvs/whispertype`
- Configuration file: Same directory as the script

## Requirements

### Optional but recommended dependencies
```bash
# For Python virtual environment, development and debugging
sudo apt install python3-setuptools-whl python3-pip-whl python3-venv python3.12-venv
sudo apt install libgirepository-1.0-dev gobject-introspection
```

### System Dependencies

```bash
# GTK and AppIndicator
sudo apt install python3-gi gir1.2-appindicator3-0.1

# Audio dependencies
sudo apt install portaudio19-dev libasound2-dev

# Keyboard simulation
sudo apt install xdotool

# Clipboard utilities
sudo apt install xclip

# Development tools
sudo apt install python3-dev python3-setuptools
```

### Python Dependencies
```bash
pip install sounddevice>=0.4.6
pip install numpy>=1.24.0
pip install requests>=2.31.0
pip install pyperclip>=1.8.2
pip install pynput>=1.7.6
pip install PyGObject>=3.42.0
```

## Installation

1. Ensure you have whisper.cpp server installed and models downloaded
2. Install the required system dependencies (see above)
3. Install the required Python packages (ideally in a Python virtual environment):
   ```bash
   python3 -m venv ~/.venvs/whispertype
   source ~/.venvs/whispertype/bin/activate
   pip install -r requirements.txt
   ```
4. Copy `config.ini` to the application directory and adjust the settings:
   ```bash
   cp config.ini.example config.ini
   # Edit config.ini with your preferred text editor
   ```
5. Install the desktop entry for XFCE menu integration:
   ```bash
   # First, make the start script executable
   chmod +x start-whispertype.sh
   
   # Edit the desktop entry file to use absolute paths
   # Replace the Exec line with the full path to the script
   sed -i "s|^Exec=.*|Exec=$(realpath start-whispertype.sh)|" whispertype.desktop
   
   # Copy the desktop entry to the applications directory
   mkdir -p ~/.local/share/applications
   cp whispertype.desktop ~/.local/share/applications/
   
   # Update the desktop database (optional, but recommended)
   update-desktop-database ~/.local/share/applications
   ```

   The application will now appear in your XFCE applications menu under the "Utility" category.
   You can also configure it to start automatically:
   1. Open XFCE's "Session and Startup" settings
   2. Go to the "Application Autostart" tab
   3. Click "Add"
   4. Name: "WhisperType"
   5. Command: Use the full path to the script (same as in the desktop entry)
   6. Description: "Voice-to-text using Whisper.cpp"

## Usage

1. Start the whisper.cpp server (or use the built-in server management)
2. Run the client using one of these methods:
   - From terminal (after activating the venv):
     ```bash
     ./start-whispertype.sh
     ```
   - From the XFCE applications menu: Look for "WhisperType" under "Multimedia" or under "Utility"
   - From the session startup: If configured, it will start automatically with your session
3. Use the system tray menu to configure settings and control the application:
   - Server Settings: Configure model, language, and translation options
   - Start/Stop Server: Control the whisper.cpp server
   - Show Audio Meter: Visual feedback during recording
   - Auto-Copy to Clipboard: Automatically copy transcribed text
   - Auto-Type Text: Automatically type transcribed text
4. Use keyboard shortcuts:
   - Hold Ctrl+Shift+Z to record, release to transcribe
   - Ctrl+Shift+T to toggle Auto-Type
   - Ctrl+Shift+X to quit 