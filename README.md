# WhisperType Cross-Platform

A cross-platform real-time speech-to-text transcription tool using whisper.cpp server. It lives in your system tray, ready to transcribe your voice with a global hotkey.

## Features

- Cross-platform system tray integration (Windows, macOS, Linux)
- Real-time audio recording with visual feedback
- Automatic transcription using whisper.cpp server
- Auto-copy to clipboard and auto-type functionality
- Server management (start/stop) from the tray menu
- Configurable model and language settings
- Translation support (foreign to English)
- Global keyboard shortcuts
- Configurable via `config.ini` file

## Requirements

### Python Dependencies
```bash
# Create and activate a virtual environment (recommended)
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### System Dependencies

#### Windows
- No additional system dependencies required

#### macOS
```bash
# Using Homebrew
brew install portaudio
```

#### Linux
```bash
# Audio dependencies
sudo apt install portaudio19-dev libasound2-dev

# Development tools
sudo apt install python3-dev python3-setuptools
```

## Installation

1. Ensure you have whisper.cpp server installed and models downloaded
2. Install the required system dependencies (see above)
3. Install the Python packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `config.ini.example` to `config.ini` and adjust the settings:
   ```bash
   cp config.ini.example config.ini
   # Edit config.ini with your preferred text editor
   ```

## Usage

1. Start the whisper.cpp server (or use the built-in server management)
2. Run the client:
   ```bash
   python whispertype.py
   ```
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

## Platform-Specific Notes

### Windows
- Uses native Windows API for keyboard simulation
- System tray integration uses Win32 API via pystray

### macOS
- Uses AppleScript for keyboard simulation
- System tray integration uses native macOS menu bar

### Linux
- Uses Xlib/XTest for keyboard simulation
- System tray integration uses native system tray protocols

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 