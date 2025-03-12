#!/usr/bin/env python3

import os
import time
import json
import wave
import tempfile
import threading
import subprocess
import numpy as np
import sounddevice as sd
import requests
import pyperclip
import sys
import configparser
import shutil
from PIL import Image
import pystray
import pyautogui
from pynput import keyboard
import platform
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

def load_config():
    """Load configuration from config.ini file"""
    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
    example_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini.example')
    
    # If config.ini doesn't exist, create it from example
    if not os.path.exists(config_path):
        if os.path.exists(example_config_path):
            shutil.copy2(example_config_path, config_path)
            print(f"Created config.ini from example file")
        else:
            print(f"Warning: Neither config.ini nor config.ini.example found")
            return None
    
    try:
        config.read(config_path)
        return config
    except configparser.Error as e:
        print(f"Error reading config file: {e}")
        return None

# Load configuration
CONFIG = load_config()

# Global settings from config
MIN_RECORDING_DURATION = float(CONFIG.get('Recording', 'min_duration', fallback='0.1'))  # seconds
REQUEST_TIMEOUT = 10  # seconds
SHOW_AUDIO_METER = CONFIG.getboolean('Defaults', 'show_audio_meter', fallback=False)
AUTO_COPY = CONFIG.getboolean('Defaults', 'auto_copy', fallback=False)
AUTO_TYPE = CONFIG.getboolean('Defaults', 'auto_type', fallback=False)

class WhisperTypeConfig:
    def __init__(self):
        self.config = CONFIG
        
    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)
        
    def getboolean(self, section, key, fallback=False):
        return self.config.getboolean(section, key, fallback=fallback)
        
    def getint(self, section, key, fallback=0):
        return self.config.getint(section, key, fallback=fallback)
        
    def getfloat(self, section, key, fallback=0.0):
        return self.config.getfloat(section, key, fallback=fallback)

class WhisperType:
    def __init__(self):
        print("[INIT] Starting WhisperType initialization...")
        self.config = WhisperTypeConfig()
        self.verbose = self.config.getboolean('Defaults', 'verbose', fallback=False)
        self.recording = False
        self.menu_recording = False  # Add this flag to track menu-triggered recording
        self.audio_data = []
        self.sample_rate = self.config.getint('Recording', 'sample_rate', 16000)
        self.temp_dir = tempfile.gettempdir()
        self.log(f"[INIT] Using temp directory: {self.temp_dir}")
        
        # Server state
        self.server_running = False
        self.server_process = None
        
        # Configure pyautogui
        self.log("[INIT] Configuring pyautogui settings...")
        pyautogui.FAILSAFE = False
        if platform.system().lower() == 'linux':
            self.log("[INIT] Linux detected, setting up X11 keyboard mapping")
            pyautogui.KEYBOARD_MAPPING = {
                'enter': 'Return',
                'tab': 'Tab',
                'space': 'space'
            }
        
        # Load configuration
        self.models_dir = os.environ.get('WHISPER_MODELS_DIR')
        if not self.models_dir:
            print("Error: WHISPER_MODELS_DIR environment variable must be set")
            sys.exit(1)
            
        default_model = CONFIG.get('Models', 'default_model', fallback='ggml-tiny.en.bin')
        self.model_path = os.path.join(self.models_dir, default_model)
        self.language = CONFIG.get('Defaults', 'language', fallback='en')
        self.port = CONFIG.get('Server', 'port', fallback='7777')
        self.translate = CONFIG.getboolean('Defaults', 'translate', fallback=False)
        
        # Enable AutoType by default
        global AUTO_TYPE
        AUTO_TYPE = True
        
        # Initialize server URL
        self.server_url = f"http://localhost:{self.port}/inference"
        
        # Initialize recording state
        self.is_recording = False
        self.audio_data = []
        self.stream = None
        self.progress_thread = None
        self.stop_progress = False
        
        # Platform-specific setup
        self.log("[INIT] Setting up platform-specific configurations...")
        self.setup_platform()
        
        # Create tray icon
        self.log("[INIT] Creating system tray icon...")
        self.create_tray_icon()
        
        # Start keyboard listener
        self.log("[INIT] Setting up keyboard listeners...")
        self.setup_keyboard_listener()
        
        # Auto-start server
        self.log("[INIT] Auto-starting server...")
        self.start_server()
        
        self.log("[INIT] WhisperType initialization complete!")

    def log(self, message):
        """Log a message to console if verbose is enabled."""
        if self.verbose:
            print(message)

    def setup_keyboard_listener(self):
        """Setup keyboard event handling"""
        def on_press(key):
            try:
                self.log(f"[KEYBOARD] Key pressed: {key}")
                if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    self.log("[KEYBOARD] Ctrl key pressed")
                    self.ctrl_pressed = True
                elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    self.log("[KEYBOARD] Shift key pressed")
                    self.shift_pressed = True
                elif hasattr(key, 'char'):
                    if key.char and key.char.upper() == 'Z' and self.ctrl_pressed and self.shift_pressed:
                        self.log("[KEYBOARD] Ctrl+Shift+Z detected, toggling recording")
                        self.start_recording()
                    elif key.char and key.char.upper() == 'X' and self.ctrl_pressed and self.shift_pressed:
                        self.log("[KEYBOARD] Ctrl+Shift+X detected, quitting application")
                        self.quit()
                    elif key.char and key.char.upper() == 'T' and self.ctrl_pressed and self.shift_pressed:
                        self.log("[KEYBOARD] Ctrl+Shift+T detected, toggling auto-type")
                        self.toggle_auto_type()
            except AttributeError as e:
                self.log(f"[KEYBOARD] AttributeError in on_press: {e}")

        def on_release(key):
            try:
                self.log(f"[KEYBOARD] Key released: {key}")
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self.log("[KEYBOARD] Ctrl key released")
                    self.ctrl_pressed = False
                elif key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
                    self.log("[KEYBOARD] Shift key released")
                    self.shift_pressed = False
                
                # Stop recording if either Ctrl or Shift is released
                if (key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.shift_l, keyboard.Key.shift_r) 
                    and not (self.ctrl_pressed and self.shift_pressed)
                    and not self.menu_recording):  # Only stop if not menu-triggered recording
                    if self.recording:
                        print("[KEYBOARD] Hotkey released, stopping recording")
                        self.stop_recording()
            except AttributeError as e:
                self.log(f"[KEYBOARD] AttributeError in on_release: {e}")

        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.start()
        self.log("[KEYBOARD] Keyboard listener started successfully")

    def setup_platform(self):
        """Setup platform-specific configurations"""
        self.platform = platform.system().lower()
        self.log(f"[PLATFORM] Detected platform: {self.platform}")
        if self.platform == 'windows':
            self.icon_path = 'icons/mic-windows.ico'
            self.recording_icon_path = 'icons/mic-recording-windows.ico'
        elif self.platform == 'darwin':  # macOS
            self.icon_path = 'icons/mic-macos.png'
            self.recording_icon_path = 'icons/mic-recording-macos.png'
        else:  # Linux
            self.icon_path = 'icons/mic-linux.png'
            self.recording_icon_path = 'icons/mic-recording-linux.png'
        self.log(f"[PLATFORM] Using icon path: {self.icon_path}")
        self.log(f"[PLATFORM] Using recording icon path: {self.recording_icon_path}")

    def create_tray_icon(self):
        """Create the system tray icon and menu"""
        self.log("[TRAY] Starting tray icon creation...")
        image = Image.open(self.icon_path) if os.path.exists(self.icon_path) else self.create_default_icon()
        self.log(f"[TRAY] Icon loaded: {self.icon_path if os.path.exists(self.icon_path) else 'default icon'}")
        
        def create_menu():
            self.log("[TRAY] Creating menu structure...")
            
            # Create model submenu
            models = []
            if os.path.exists(self.models_dir):
                models = sorted([f for f in os.listdir(self.models_dir) if f.endswith('.bin')])
            
            def create_model_item(model_name):
                return pystray.MenuItem(
                    model_name,
                    lambda item: self.change_model(model_name),
                    checked=lambda item: os.path.basename(self.model_path) == model_name,
                    radio=True
                )

            # Create language submenu
            common_languages = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'pl', 'ru', 'uk', 'zh', 'ja', 'ko']
            def create_language_item(lang_code):
                return pystray.MenuItem(
                    lang_code,
                    lambda item: self.change_language(lang_code),
                    checked=lambda item: self.language == lang_code,
                    radio=True
                )

            # Create port submenu
            common_ports = ['7777', '7778', '7779', '7780']
            def create_port_item(port):
                return pystray.MenuItem(
                    port,
                    lambda item: self.change_port(port),
                    checked=lambda item: self.port == port,
                    radio=True
                )

            # Create settings submenu
            settings_menu = pystray.Menu(
                pystray.MenuItem("Model", pystray.Menu(*[create_model_item(model) for model in models])),
                pystray.MenuItem("Language", pystray.Menu(*(
                    create_language_item(lang) for lang in common_languages
                ))),
                pystray.MenuItem("Port", pystray.Menu(*(
                    create_port_item(port) for port in common_ports
                ))),
                pystray.MenuItem("Translation", lambda item: self.toggle_translation(), checked=lambda item: self.translate),
                pystray.MenuItem("Show Audio Meter", lambda item: self.toggle_audio_meter(), checked=lambda item: SHOW_AUDIO_METER),
            )
            
            menu = (
                pystray.MenuItem("Auto-Type Text (Ctrl+Shift+T)", lambda item: self.toggle_auto_type(), checked=lambda item: AUTO_TYPE),
                pystray.MenuItem("Auto-Copy to Clipboard", lambda item: self.toggle_auto_copy(), checked=lambda item: AUTO_COPY),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Record (Ctrl+Shift+Z)", lambda item: self.toggle_recording(), checked=lambda item: self.recording),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Start Server", lambda item: self.start_server(), enabled=lambda item: not self.server_running),
                pystray.MenuItem("Stop Server", lambda item: self.stop_server(), enabled=lambda item: self.server_running),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Settings", settings_menu),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit (Ctrl+Shift+X)", lambda item: self.quit())
            )
            self.log("[TRAY] Menu structure created successfully")
            return menu
        
        self.log("[TRAY] Initializing system tray icon...")
        self.tray_icon = pystray.Icon(
            name="whispertype",
            icon=image,
            title="WhisperType - Server Stopped",  # Initial title
            menu=create_menu()
        )
        
        # Update title with server status
        self.update_tray_status()
        
        # Check if menu is supported
        self.log("[TRAY] Checking menu support...")
        if hasattr(self.tray_icon, 'HAS_MENU'):
            has_menu = self.tray_icon.HAS_MENU
            self.log(f"[TRAY] Menu support: {'Yes' if has_menu else 'No'}")
            if not has_menu:
                self.log("[TRAY] WARNING: Menu support is not available. You may need to install system GTK packages.")
                self.log("[TRAY] Try: sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0")
        
        self.log(f"[TRAY] Tray icon backend: {type(self.tray_icon).__module__}.{type(self.tray_icon).__name__}")
        self.log("[TRAY] Tray icon initialized")

    def update_tray_status(self):
        """Update tray icon title with current status"""
        status = "Running" if self.server_running else "Stopped"
        model_name = os.path.basename(self.model_path)
        title = f"WhisperType - Server {status}\nModel: {model_name}\nLanguage: {self.language}"
        self.tray_icon.title = title

    def change_language(self, lang_code):
        """Change the language setting"""
        self.log(f"[SETTINGS] Changing language to: {lang_code}")
        restart_server = False
        
        if self.server_running:
            self.log("[SETTINGS] Server is running, will restart after language change")
            restart_server = True
            
        # Update language
        self.language = lang_code
        
        # Save to config
        self.config.config.set('Defaults', 'language', lang_code)
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
        with open(config_path, 'w') as f:
            self.config.config.write(f)
            
        self.log("[SETTINGS] Language changed and config saved")
        
        # Update tray status
        self.update_tray_status()
        
        # Restart server if it was running
        if restart_server:
            self.log("[SETTINGS] Restarting server with new language...")
            self.stop_server()
            self.start_server()

    def change_port(self, port):
        """Change the server port"""
        self.log(f"[SETTINGS] Changing port to: {port}")
        restart_server = False
        
        if self.server_running:
            self.log("[SETTINGS] Server is running, will restart after port change")
            restart_server = True
            
        # Update port
        self.port = port
        self.server_url = f"http://localhost:{self.port}/inference"
        
        # Save to config
        self.config.config.set('Server', 'port', port)
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
        with open(config_path, 'w') as f:
            self.config.config.write(f)
            
        self.log("[SETTINGS] Port changed and config saved")
        
        # Restart server if it was running
        if restart_server:
            self.log("[SETTINGS] Restarting server with new port...")
            self.stop_server()
            self.start_server()

    def toggle_translation(self):
        """Toggle translation setting"""
        self.log("[SETTINGS] Toggling translation...")
        restart_server = False
        
        if self.server_running:
            self.log("[SETTINGS] Server is running, will restart after translation change")
            restart_server = True
            
        # Update translation setting
        self.translate = not self.translate
        
        # Save to config
        self.config.config.set('Defaults', 'translate', str(self.translate))
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
        with open(config_path, 'w') as f:
            self.config.config.write(f)
            
        self.log("[SETTINGS] Translation setting changed and config saved")
        
        # Restart server if it was running
        if restart_server:
            self.log("[SETTINGS] Restarting server with new translation setting...")
            self.stop_server()
            self.start_server()

    def change_model(self, model_name):
        """Change the Whisper model"""
        self.log(f"[MODEL] Changing model to: {model_name}")
        restart_server = False
        
        if self.server_running:
            self.log("[MODEL] Server is running, will restart after model change")
            restart_server = True
            
        # Update model path
        self.model_path = os.path.join(self.models_dir, model_name)
        
        # Save to config
        self.config.config.set('Models', 'default_model', model_name)
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
        with open(config_path, 'w') as f:
            self.config.config.write(f)
            
        self.log("[MODEL] Model changed and config saved")
        
        # Restart server if it was running
        if restart_server:
            self.log("[MODEL] Restarting server with new model...")
            self.stop_server()
            self.start_server()

    def start_server(self):
        """Start the whisper server"""
        if self.server_running:
            self.log("[SERVER] Server is already running")
            return
            
        try:
            # Get models directory from environment or config
            models_dir = os.getenv('WHISPER_MODELS_DIR')
            if not models_dir:
                self.log("[SERVER] Error: WHISPER_MODELS_DIR environment variable not set")
                return
                
            model_path = os.path.join(
                models_dir,
                self.config.get('Models', 'default_model')
            )
            
            if not os.path.exists(model_path):
                self.log("[SERVER] Model file not found:", model_path)
                return
            
            cmd_template = self.config.get('Server Command', 'command')
            cmd = cmd_template.format(
                model_path=model_path,
                language=self.config.get('Defaults', 'language', 'en'),
                port=self.config.get('Server', 'port', '7777')
            )
            
            if self.config.getboolean('Defaults', 'translate', False):
                cmd += ' -tr'
            
            self.log(f"[SERVER] Starting server with command: {cmd}")
            self.server_process = subprocess.Popen(cmd.split())
            self.server_running = True
            self.log("[SERVER] Server starting...")
            
            # Update menu items and tray status
            self.tray_icon.update_menu()
            self.update_tray_status()
            
        except Exception as e:
            self.log(f"[SERVER] Error starting server: {e}")
            self.server_running = False
            self.server_process = None

    def stop_server(self):
        """Stop the whisper server"""
        if not self.server_running:
            self.log("[SERVER] Server is not running")
            return
            
        try:
            self.log("[SERVER] Stopping server...")
            if self.platform == 'windows':
                subprocess.run(['taskkill', '/F', '/IM', 'whisper-server.exe'])
            else:
                subprocess.run(['pkill', '-f', 'whisper-server'])
            
            if self.server_process:
                self.server_process.terminate()
                self.server_process = None
                
            self.server_running = False
            self.log("[SERVER] Server stopped")
            
            # Update menu items and tray status
            self.tray_icon.update_menu()
            self.update_tray_status()
            
        except Exception as e:
            self.log(f"[SERVER] Error stopping server: {e}")

    def toggle_audio_meter(self):
        """Toggle audio meter display"""
        global SHOW_AUDIO_METER
        SHOW_AUDIO_METER = not SHOW_AUDIO_METER

    def toggle_auto_copy(self):
        """Toggle auto-copy to clipboard"""
        global AUTO_COPY
        AUTO_COPY = not AUTO_COPY

    def toggle_auto_type(self):
        """Toggle auto-type functionality"""
        global AUTO_TYPE
        self.log("[AUTO-TYPE] Toggling auto-type...")
        AUTO_TYPE = not AUTO_TYPE
        self.log(f"[AUTO-TYPE] Auto-Type is now {'enabled' if AUTO_TYPE else 'disabled'}")
        # Update menu item state if menu is available
        if hasattr(self.tray_icon, 'menu'):
            self.log("[AUTO-TYPE] Updating menu item state...")
            for item in self.tray_icon.menu:
                if isinstance(item, pystray.MenuItem) and item.text == "Auto-Type Text":
                    item._checked = AUTO_TYPE
                    self.log("[AUTO-TYPE] Menu item state updated")
                    break

    def quit(self):
        """Quit the application"""
        self.log("[APP] Shutting down...")
        self.running = False
        if self.recording:
            self.stop_recording()
        if self.server_running:
            self.stop_server()
        self.tray_icon.stop()
        self.log("[APP] Shutdown complete")

    def start_recording(self):
        """Start recording audio"""
        if not self.recording:
            self.recording = True
            self.audio_data = []
            self.recording_start_time = time.time()
            self.log("\nRecording started... Hold Ctrl+Shift+Z to continue recording.")
            threading.Thread(target=self.record_audio).start()
            
            # Update tray icon
            if os.path.exists(self.recording_icon_path):
                self.tray_icon.icon = Image.open(self.recording_icon_path)

    def stop_recording(self):
        """Stop recording and process audio"""
        if self.recording:
            self.recording = False
            recording_duration = time.time() - self.recording_start_time
            
            # Restore normal icon
            if os.path.exists(self.icon_path):
                self.tray_icon.icon = Image.open(self.icon_path)
            
            if recording_duration < self.config.getfloat('Recording', 'min_duration', 0.1):
                self.log(f"Recording too short ({recording_duration:.1f}s), discarding...")
                self.audio_data = []
                return
                
            self.log("Recording stopped, processing...")
            
            audio_file = self.save_audio()
            if audio_file:
                self.log("Sending to whisper.cpp server...")
                transcribed_text = self.transcribe_audio(audio_file)
                if transcribed_text:
                    self.log(f"Transcribed: {transcribed_text}")
                    self.handle_transcribed_text(transcribed_text)
                else:
                    self.log("No transcription received")
                os.remove(audio_file)

    def record_audio(self):
        """Record audio in a separate thread"""
        def callback(indata, frames, time, status):
            if status:
                self.log(status)
            if self.recording:
                self.audio_data.extend(indata.copy())

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback):
                while self.recording:
                    sd.sleep(100)
        except Exception as e:
            self.log(f"Error recording audio: {e}")
            self.recording = False

    def save_audio(self):
        """Save recorded audio to a temporary file"""
        if not self.audio_data:
            return None
            
        try:
            audio_data = np.concatenate(self.audio_data)
            temp_file = os.path.join(self.temp_dir, 'whispertype_recording.wav')
            
            with wave.open(temp_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())
            
            return temp_file
        except Exception as e:
            self.log(f"Error saving audio: {e}")
            return None

    def transcribe_audio(self, audio_file):
        """Send audio file to whisper.cpp server for transcription"""
        try:
            with open(audio_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    self.server_url,
                    files=files,
                    timeout=10
                )
                
            if response.status_code == 200:
                result = response.json()
                text = result.get('text', '').strip()
                return ' '.join(text.split())
            else:
                self.log(f"Error: Server returned status code {response.status_code}")
                if response.text:
                    self.log(f"Server response: {response.text[:200]}")
                return None
        except Exception as e:
            self.log(f"Error transcribing audio: {e}")
            return None

    def handle_transcribed_text(self, text):
        """Handle transcribed text (copy to clipboard and/or type)"""
        self.log("[TEXT-HANDLER] Starting to handle transcribed text...")
        if not text:
            self.log("[TEXT-HANDLER] No text to handle")
            return
            
        try:
            # Copy to clipboard if enabled
            if AUTO_COPY:
                self.log("[TEXT-HANDLER] Auto-copy enabled, copying to clipboard...")
                pyperclip.copy(text)
                self.log("[TEXT-HANDLER] Text copied to clipboard successfully")
            
            # Type text if enabled
            if AUTO_TYPE:
                self.log("[TEXT-HANDLER] Auto-Type enabled, preparing to type text...")
                try:
                    self.log("[TEXT-HANDLER] Adding delay before typing...")
                    time.sleep(0.5)
                    self.log("[TEXT-HANDLER] Starting to type text...")
                    pyautogui.write(text)
                    self.log("[TEXT-HANDLER] Text typed successfully")
                except Exception as e:
                    self.log(f"[TEXT-HANDLER] Error during typing: {e}")
            else:
                self.log("[TEXT-HANDLER] Auto-Type is disabled, skipping typing")
        except Exception as e:
            self.log(f"[TEXT-HANDLER] Error in handle_transcribed_text: {e}")

    def toggle_recording(self):
        """Toggle recording state (for menu-triggered recording)"""
        if self.recording:
            self.menu_recording = False
            self.stop_recording()
        else:
            self.menu_recording = True
            self.start_recording()

def main():
    print("[MAIN] WhisperType starting...")
    print("[MAIN] Hold Ctrl+Shift+Z to record.")
    print("[MAIN] Press Ctrl+Shift+X to quit.")
    
    try:
        print("[MAIN] Creating WhisperType instance...")
        client = WhisperType()
        print("[MAIN] Starting main loop...")
        client.tray_icon.run()
        print("[MAIN] Main loop running...")
    except Exception as e:
        print(f"[MAIN] Error in main function: {e}")
        if platform.system().lower() == 'linux':
            print("[MAIN] On Linux, you may need to install GTK packages:")
            print("[MAIN] Try: sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0")

if __name__ == "__main__":
    print("[STARTUP] Initializing global settings...")
    # Initialize global settings
    SHOW_AUDIO_METER = False
    AUTO_COPY = False
    AUTO_TYPE = True  # Set default to True
    print("[STARTUP] Global settings initialized")
    
    main() 