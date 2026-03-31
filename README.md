# WhisperType

A cross-platform real-time speech-to-text transcription tool using [whisper.cpp](https://github.com/ggerganov/whisper.cpp) server. Lives in your system tray — hold a hotkey to record, release to transcribe.

## Features

- System tray integration (Linux (tested on XFCE) / Windows / macOS (untested))
- Real-time audio recording with optional visual meter
- Transcription via a local whisper.cpp server process
- Auto-copy to clipboard and auto-type
- Server start/stop from the tray menu
- Configurable model, language, and translation settings
- Global keyboard shortcuts
- GUI setup wizard (`installer.py`) for first-time configuration

## Quick start

### Linux / macOS

```bash
# 1. Install system dependencies (see below)
# 2. Run the installer — creates the venv, installs Python deps, and launches the app
./install.sh

# Optional: specify a custom venv location
./install.sh /path/to/my/venv
```

`install.sh` creates the venv (default `~/.venvs/whispertype`), installs `requirements.txt`, then hands off to `start-whispertype.sh` which opens the setup wizard on first run.

### Windows

```bat
install.bat
REM or with a custom venv:
install.bat C:\Users\you\venvs\whispertype
```

`install.bat` does the same: creates the venv (default `%LOCALAPPDATA%\whispertype\venv`), installs deps, calls `start-whispertype.bat`.

### Subsequent launches

```bash
./start-whispertype.sh   # Linux/macOS
start-whispertype.bat    # Windows
```

The start scripts resolve the venv automatically (from the `WHISPERTYPE_VENV` env var set by the install script, or from `venv_path` in `config.ini` / `config.ini.example` as fallback).

### Linux desktop entry

```bash
./install-desktop.sh
```

Installs a `.desktop` file so WhisperType appears in your application launcher.

---

## System dependencies

### Linux (Debian/Ubuntu)

```bash
sudo apt install \
    portaudio19-dev libasound2-dev libportaudiocpp0 \
    libcairo2-dev libgirepository-1.0-dev libappindicator3-dev \
    python3-tk python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    xdotool xclip libxdo3 libxkbcommon-dev \
    blt tk8.6-blt2.5 python3-dev python3-setuptools
```

### macOS

```bash
brew install portaudio
```

### Windows

No additional system dependencies required.

---

## Setup wizard

`config.ini` is **only written when you click Save** in the wizard — nothing is created or copied on startup or if you cancel.

The wizard opens automatically on first run (or whenever `whisper-server` / the default model is missing). You can also run it any time:

```bash
python installer.py          # uses config.ini next to the script
python installer.py /path/to/config.ini
```

Or from the tray menu: **Setup whisper.cpp / models…**

### Wizard steps

| Step | What happens |
|------|--------------|
| **0 – Welcome** | Overview of what the wizard does |
| **1 – Binary** | Point to your `whisper-server` executable. On Windows you can download an official release zip directly from the wizard. On Linux/macOS build from source ([quick start](https://github.com/ggml-org/whisper.cpp#quick-start)) and browse to the binary. |
| **2 – Models** | Set the models folder (pre-filled to `<whisper-server dir>/models`). Optionally download GGML weights from Hugging Face — the same set as upstream [`download-ggml-model.sh`](https://github.com/ggml-org/whisper.cpp/blob/master/models/download-ggml-model.sh). Skip download if `.bin` files already exist. |
| **3 – Default model** | Pick which model WhisperType starts with. Must select one before Save is enabled. |

**Save** performs an atomic `os.replace(draft → config.ini)` — the file either appears complete or not at all.

If an existing `config.ini` is loaded, a banner shows exactly what is still missing (broken path, no model files, etc.).

---

## Usage

1. Launch via `start-whispertype.sh` (or `start-whispertype.bat`).
2. The tray icon appears. Start the whisper.cpp server from the tray if needed.
3. Hold **Ctrl+Shift+Z** to record; release to transcribe.
4. Tray menu options:
   - **Start / Stop Server** — manage the whisper.cpp process
   - **Server Settings** — model, language, port, translation
   - **Show Audio Meter** — visual recording feedback
   - **Auto-Copy to Clipboard** — copy transcription automatically
   - **Auto-Type Text** — type transcription into the focused window
   - **Setup whisper.cpp / models…** — reopen the wizard

### Keyboard shortcuts (defaults)

| Shortcut | Action |
|----------|--------|
| Hold Ctrl+Shift+Z | Record (release to transcribe) |
| Ctrl+Shift+T | Toggle Auto-Type |
| Ctrl+Shift+X | Quit |

Shortcuts are configurable in `config.ini` under `[Shortcuts]`.

---

## Configuration

`config.ini` uses Python's `configparser` with `ExtendedInterpolation`. Placeholders like `${HOME}/...` are expanded via `os.path.expandvars` / `os.path.expanduser`. See `config.ini.example` for all available keys and defaults.

Key sections:

| Section | Purpose |
|---------|---------|
| `[Server]` | `command` template, `host`, `port`, `url` |
| `[Models]` | `models_dir`, `default_model` |
| `[Paths]` | `whisper_install_dir`, `venv_path` |
| `[Recording]` | `min_duration`, `sample_rate` |
| `[Defaults]` | `language`, `auto_copy`, `auto_type`, `translate`, etc. |
| `[UI]` | `theme`, `enable_sounds`, `typing_delay` |
| `[Shortcuts]` | `record`, `quit`, `toggle_type` |

---

## Platform notes

| Platform | Status |
|----------|--------|
| Linux (Ubuntu 24.04, XFCE) | Tested |
| Windows | Untested |
| macOS | Untested |

---

## Contributing

Contributions welcome — please open a Pull Request.
