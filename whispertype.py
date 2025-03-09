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
import soundfile as sf
import requests
import pyperclip
import sys
import gi
import socket
import configparser
import shutil
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib
from pynput import keyboard

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

class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent, models_dir, current_settings):
        super().__init__(title="Server Settings", parent=None, flags=0)
        self.set_modal(True)
        self.set_default_size(300, 150)
        
        box = self.get_content_area()
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(6)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)
        
        # Model selection
        model_label = Gtk.Label(label="Model:")
        grid.attach(model_label, 0, 0, 1, 1)
        
        self.model_combo = Gtk.ComboBoxText()
        if os.path.exists(models_dir):
            models = [f for f in os.listdir(models_dir) if f.endswith('.bin')]
            for model in sorted(models):
                self.model_combo.append_text(model)
                if os.path.join(models_dir, model) == current_settings['model_path']:
                    self.model_combo.set_active_id(model)
        grid.attach(self.model_combo, 1, 0, 1, 1)
        
        # Language selection
        lang_label = Gtk.Label(label="Language:")
        grid.attach(lang_label, 0, 1, 1, 1)
        
        self.lang_entry = Gtk.Entry()
        self.lang_entry.set_text(current_settings['language'])
        self.lang_entry.set_width_chars(5)
        grid.attach(self.lang_entry, 1, 1, 1, 1)
        
        # Port selection
        port_label = Gtk.Label(label="Port:")
        grid.attach(port_label, 0, 2, 1, 1)
        
        self.port_entry = Gtk.Entry()
        self.port_entry.set_text(current_settings['port'])
        self.port_entry.set_width_chars(5)
        grid.attach(self.port_entry, 1, 2, 1, 1)
        
        # Translation checkbox
        self.translate_check = Gtk.CheckButton(label="Enable translation to English")
        self.translate_check.set_active(current_settings.get('translate', False))
        grid.attach(self.translate_check, 0, 3, 2, 1)
        
        box.add(grid)
        
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("OK", Gtk.ResponseType.OK)
        
        self.show_all()

    def get_settings(self):
        return {
            'model': self.model_combo.get_active_text(),
            'language': self.lang_entry.get_text().strip(),
            'port': self.port_entry.get_text().strip(),
            'translate': self.translate_check.get_active()
        }

class WhisperTypeIndicator:
    def __init__(self, client):
        self.client = client
        self.indicator = AppIndicator3.Indicator.new(
            "whispertype",
            "audio-input-microphone",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        
        # Server settings from config
        self.models_dir = os.environ.get('WHISPER_MODELS_DIR')
        if not self.models_dir:
            print("Error: WHISPER_MODELS_DIR environment variable must be set")
            sys.exit(1)
            
        default_model = CONFIG.get('Models', 'default_model', fallback='ggml-tiny.en.bin')
        self.model_path = os.path.join(self.models_dir, default_model)
        self.language = CONFIG.get('Defaults', 'language', fallback='en')
        self.port = CONFIG.get('Server', 'port', fallback='7777')
        self.translate = CONFIG.getboolean('Defaults', 'translate', fallback=False)
        
        self.setup_menu()
        self.update_status()

    def setup_menu(self):
        menu = Gtk.Menu()

        # Status items (not clickable)
        self.status_item = Gtk.MenuItem(label="Status: Ready")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        # Server status (not clickable)
        self.server_label = Gtk.MenuItem(label="Server: Checking...")
        self.server_label.set_sensitive(False)
        menu.append(self.server_label)

        # Keyboard shortcuts info (not clickable)
        shortcuts_item = Gtk.MenuItem(label="Keyboard Shortcuts:")
        shortcuts_item.set_sensitive(False)
        menu.append(shortcuts_item)
        
        record_shortcut = Gtk.MenuItem(label="   Ctrl+Shift+Z: Record")
        record_shortcut.set_sensitive(False)
        menu.append(record_shortcut)
        
        type_toggle_shortcut = Gtk.MenuItem(label="   Ctrl+Shift+T: Toggle Auto-Type")
        type_toggle_shortcut.set_sensitive(False)
        menu.append(type_toggle_shortcut)
        
        quit_shortcut = Gtk.MenuItem(label="   Ctrl+Shift+X: Quit")
        quit_shortcut.set_sensitive(False)
        menu.append(quit_shortcut)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Server settings
        settings_item = Gtk.MenuItem(label="Server Settings...")
        settings_item.connect("activate", self.show_settings_dialog)
        menu.append(settings_item)

        # Server control buttons
        self.start_server_button = Gtk.MenuItem(label="Start Server")
        self.start_server_button.connect("activate", self.start_server)
        self.start_server_button.set_sensitive(False)  # Initially disabled
        menu.append(self.start_server_button)

        self.stop_server_button = Gtk.MenuItem(label="Stop Server")
        self.stop_server_button.connect("activate", self.stop_server)
        self.stop_server_button.set_sensitive(False)  # Initially disabled
        menu.append(self.stop_server_button)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Toggle audio meter
        self.meter_item = Gtk.CheckMenuItem(label="Show Audio Meter")
        self.meter_item.set_active(SHOW_AUDIO_METER)
        self.meter_item.connect("activate", self.toggle_audio_meter)
        menu.append(self.meter_item)

        # Toggle auto-copy
        self.copy_item = Gtk.CheckMenuItem(label="Auto-Copy to Clipboard")
        self.copy_item.set_active(AUTO_COPY)
        self.copy_item.connect("activate", self.toggle_auto_copy)
        menu.append(self.copy_item)

        # Toggle auto-type
        self.type_item = Gtk.CheckMenuItem(label="Auto-Type Text (Ctrl+Shift+T)")
        self.type_item.set_active(AUTO_TYPE)
        self.type_item.connect("activate", self.toggle_auto_type)
        menu.append(self.type_item)

        # Separator
        menu.append(Gtk.SeparatorMenuItem())

        # Quit item
        quit_item = Gtk.MenuItem(label="Quit (Ctrl+Shift+X)")
        quit_item.connect("activate", self.quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def show_settings_dialog(self, widget):
        """Show the settings dialog"""
        current_settings = {
            'model_path': self.model_path,
            'language': self.language,
            'port': self.port,
            'translate': self.translate
        }
        dialog = SettingsDialog(None, self.models_dir, current_settings)
        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            settings = dialog.get_settings()
            if settings['model']:
                self.model_path = os.path.join(self.models_dir, settings['model'])
            if settings['language']:
                self.language = settings['language']
            if settings['port']:
                self.port = settings['port']
                self.client.server_url = f"http://localhost:{self.port}/inference"
            self.translate = settings['translate']
        
        dialog.destroy()

    def update_status(self):
        if self.client.recording:
            self.status_item.set_label("Status: Recording...")
            self.indicator.set_icon("microphone-sensitivity-high")  # Green mic icon
        else:
            self.status_item.set_label("Status: Ready")
            # Update icon based on server status and auto-type
            self.update_icon()
        return True

    def update_icon(self):
        """Update the indicator icon based on server status and auto-type"""
        try:
            # Check server status
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', int(self.port)))
            sock.close()
            
            if result == 0:  # Server is running
                if AUTO_TYPE:
                    self.indicator.set_icon("input-keyboard")  # Keyboard icon when auto-type is on
                else:
                    self.indicator.set_icon("audio-input-microphone")  # Normal mic icon
            else:
                self.indicator.set_icon("audio-input-microphone-muted")  # Muted icon when server is down
        except Exception:
            self.indicator.set_icon("audio-input-microphone-muted")

    def check_server(self):
        try:
            # Try to connect to the server socket instead of making a GET request
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', int(self.port)))
            sock.close()
            
            if result == 0:  # Port is open
                self.server_label.set_label("Server: Ready")
                self.start_server_button.set_sensitive(False)  # Disable start button when server is running
                self.stop_server_button.set_sensitive(True)   # Enable stop button when server is running
                self.update_icon()  # Update icon based on auto-type status
            else:
                self.server_label.set_label("Server: Not Available")
                self.start_server_button.set_sensitive(True)  # Enable start button when server is not running
                self.stop_server_button.set_sensitive(False)  # Disable stop button when server is not running
                self.indicator.set_icon("audio-input-microphone-muted")
        except Exception:
            self.server_label.set_label("Server: Not Available")
            self.start_server_button.set_sensitive(True)  # Enable start button when server is not running
            self.stop_server_button.set_sensitive(False)  # Disable stop button when server is not running
            self.indicator.set_icon("audio-input-microphone-muted")
        return True

    def start_server(self, widget):
        """Start the whisper server with current settings"""
        try:
            # Use current stored settings
            if not os.path.exists(self.model_path):
                print("Model file not found:", self.model_path)
                return
            
            # Get server command from config and format it with current settings
            cmd_template = CONFIG.get('Server Command', 'command', 
                                    fallback='whisper-server -m {model_path} -l {language} --port {port}')
            cmd = cmd_template.format(
                model_path=self.model_path,
                language=self.language,
                port=self.port
            )
            
            # Add translation flag if enabled
            if self.translate:
                cmd += ' -tr'
            
            # Split command into list for Popen
            cmd = cmd.split()
            
            self.server_process = subprocess.Popen(cmd, 
                                                 stdout=subprocess.PIPE, 
                                                 stderr=subprocess.PIPE)
            self.server_label.set_label("Server: Starting...")
            self.start_server_button.set_sensitive(False)  # Disable start button while starting
            self.stop_server_button.set_sensitive(True)   # Enable stop button while starting
            # Force an immediate server check after a short delay
            GLib.timeout_add(2000, self.check_server)
        except Exception as e:
            print(f"Error starting server: {e}")
            self.server_label.set_label("Server: Start Failed")
            self.start_server_button.set_sensitive(True)  # Re-enable start button if start fails
            self.stop_server_button.set_sensitive(False)  # Disable stop button if start fails

    def stop_server(self, widget):
        """Stop the whisper server"""
        try:
            # Find whisper-server process
            result = subprocess.run(['pkill', '-f', 'whisper-server'], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
            if result.returncode == 0:
                self.server_label.set_label("Server: Stopping...")
                # Force an immediate server check after a short delay
                GLib.timeout_add(2000, self.check_server)
            else:
                print("No whisper-server process found")
                self.server_label.set_label("Server: Not Available")
                self.start_server_button.set_sensitive(True)
                self.stop_server_button.set_sensitive(False)
                self.indicator.set_icon("audio-input-microphone-muted")
        except Exception as e:
            print(f"Error stopping server: {e}")
            self.server_label.set_label("Server: Stop Failed")

    def toggle_audio_meter(self, widget):
        global SHOW_AUDIO_METER
        SHOW_AUDIO_METER = widget.get_active()

    def toggle_auto_copy(self, widget):
        global AUTO_COPY
        AUTO_COPY = widget.get_active()

    def toggle_auto_type(self, widget):
        global AUTO_TYPE
        AUTO_TYPE = widget.get_active()
        self.update_icon()  # Update icon when auto-type is toggled

    def quit(self, widget):
        self.client.running = False
        if self.client.recording:
            self.client.stop_recording()
        Gtk.main_quit()

class WhisperType:
    def __init__(self):
        self.recording = False
        self.audio_data = []
        self.sample_rate = int(CONFIG.get('Recording', 'sample_rate', fallback='16000'))
        self.temp_dir = tempfile.gettempdir()
        
        # Server settings from config
        host = CONFIG.get('Server', 'host', fallback='localhost')
        port = CONFIG.get('Server', 'port', fallback='7777')
        self.server_url = f"http://{host}:{port}/inference"
        
        self.recording_start_time = None
        self.last_audio_level = 0
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.running = True
        
        # Setup keyboard listeners
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release)
        self.listener.start()

        # Check server availability
        try:
            requests.get(self.server_url, timeout=1)
        except Exception as e:
            print(f"Warning: Error checking server: {e}")

    def on_press(self, key):
        """Handle key press events"""
        try:
            if key == keyboard.Key.ctrl:
                self.ctrl_pressed = True
            elif key == keyboard.Key.shift:
                self.shift_pressed = True
            elif hasattr(key, 'char'):
                if key.char == 'Z' and self.ctrl_pressed and self.shift_pressed:
                    self.start_recording()
                elif key.char == 'X' and self.ctrl_pressed and self.shift_pressed:
                    print("\nQuitting...")
                    self.running = False
                    Gtk.main_quit()
                    if self.recording:
                        self.stop_recording()
                elif key.char == 'T' and self.ctrl_pressed and self.shift_pressed:
                    global AUTO_TYPE
                    AUTO_TYPE = not AUTO_TYPE
                    self.type_item.set_active(AUTO_TYPE)
                    print(f"\nAuto-Type {'enabled' if AUTO_TYPE else 'disabled'}")
        except AttributeError:
            pass

    def on_release(self, key):
        """Handle key release events"""
        try:
            if key == keyboard.Key.ctrl:
                self.ctrl_pressed = False
                if self.recording:
                    self.stop_recording()
            elif key == keyboard.Key.shift:
                self.shift_pressed = False
                if self.recording:
                    self.stop_recording()
            elif hasattr(key, 'char') and key.char == 'R' and self.recording:
                self.stop_recording()
        except AttributeError:
            pass

    def show_audio_level(self, level):
        """Display audio level meter"""
        if not self.recording or not SHOW_AUDIO_METER:  # Don't show meter if we're not recording or it's disabled
            return
        bars = min(int(level * 20), 20)  # Scale to 20 characters and cap it
        meter = '▁' * bars + ' ' * (20 - bars)
        sys.stdout.write('\rRecording [' + meter + ']')
        sys.stdout.flush()

    def start_recording(self):
        """Start recording"""
        if not self.recording:
            self.recording = True
            self.audio_data = []
            self.recording_start_time = time.time()
            print("\nRecording started... Hold Ctrl+Shift+Z to continue recording.")
            threading.Thread(target=self.record_audio).start()

    def stop_recording(self):
        """Stop recording and process"""
        if self.recording:
            self.recording = False
            if SHOW_AUDIO_METER:
                sys.stdout.write('\r' + ' ' * 50 + '\r')  # Clear audio meter line
            recording_duration = time.time() - self.recording_start_time
            
            if recording_duration < MIN_RECORDING_DURATION:
                print(f"Recording too short ({recording_duration:.1f}s), discarding...")
                self.audio_data = []
                return
                
            print("Recording stopped, processing...")
            
            # Pad very short recordings with silence
            if recording_duration < 0.5:  # Add padding for recordings under 0.5s
                padding_samples = int(0.5 * self.sample_rate) - len(self.audio_data)
                if padding_samples > 0:
                    self.audio_data.extend([np.zeros((1,), dtype=np.float32)] * padding_samples)
            
            audio_file = self.save_audio()
            if audio_file:
                print("Sending to whisper.cpp server...")
                self.show_progress()
                transcribed_text = self.transcribe_audio(audio_file)
                sys.stdout.write('\r' + ' ' * 70 + '\r')  # Clear progress line
                if transcribed_text:
                    print(f"Transcribed: {transcribed_text}")
                    self.type_text(transcribed_text)
                else:
                    print("No transcription received")
                os.remove(audio_file)

    def show_progress(self):
        """Show a progress indicator while waiting for transcription"""
        def progress_thread():
            chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            i = 0
            while self.transcribing:
                sys.stdout.write('\r' + chars[i] + ' Transcribing...')
                sys.stdout.flush()
                i = (i + 1) % len(chars)
                time.sleep(0.1)
            sys.stdout.write('\r' + ' ' * 20 + '\r')
            sys.stdout.flush()

        self.transcribing = True
        threading.Thread(target=progress_thread).start()

    def record_audio(self):
        """Record audio in a separate thread"""
        def callback(indata, frames, time, status):
            if status:
                print(status)
            if self.recording:
                # Calculate audio level (RMS)
                self.last_audio_level = np.sqrt(np.mean(indata**2))
                if SHOW_AUDIO_METER:
                    self.show_audio_level(self.last_audio_level)
                self.audio_data.extend(indata.copy())

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback):
                while self.recording:
                    sd.sleep(100)
        except Exception as e:
            print(f"Error recording audio: {e}")
            self.recording = False

    def save_audio(self):
        """Save recorded audio to a temporary WAV file"""
        if not self.audio_data or len(self.audio_data) == 0:
            print("No audio data recorded")
            return None
            
        try:
            audio_array = np.concatenate(self.audio_data, axis=0)
            if len(audio_array) == 0:
                print("Empty audio recording")
                return None
                
            # Normalize audio to prevent very quiet recordings
            max_val = np.max(np.abs(audio_array))
            if max_val > 0:
                audio_array = audio_array / max_val * 0.9  # Scale to 90% of maximum
                
            temp_file = os.path.join(self.temp_dir, "whisper_recording.wav")
            
            with wave.open(temp_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_array * 32767).astype(np.int16).tobytes())
            
            return temp_file
        except Exception as e:
            print(f"Error saving audio: {e}")
            return None

    def transcribe_audio(self, audio_file):
        """Send audio file to whisper.cpp server for transcription"""
        try:
            with open(audio_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(self.server_url, files=files, timeout=REQUEST_TIMEOUT)
                
            if response.status_code == 200:
                result = response.json()
                self.transcribing = False
                # Clean up the text: replace multiple newlines/spaces with a single space
                text = result.get('text', '').strip()
                text = ' '.join(text.split())
                return text
            else:
                print(f"Error: Server returned status code {response.status_code}")
                if response.text:
                    print(f"Server response: {response.text[:200]}")
                self.transcribing = False
                return None
        except Exception as e:
            print(f"Error transcribing audio: {e}")
            self.transcribing = False
            return None

    def type_text(self, text):
        """Type text using xdotool"""
        if not text:
            return
            
        try:
            # Copy to clipboard if enabled
            if AUTO_COPY:
                pyperclip.copy(text)
                print("Text copied to clipboard!")
            
            # Type text if enabled
            if AUTO_TYPE:
                subprocess.run(['xdotool', 'type', text], check=True)
                print("Text typed successfully!")
        except subprocess.CalledProcessError as e:
            print(f"Error using xdotool: {e}")
        except Exception as e:
            print(f"Error handling text: {e}")

def main():
    print("WhisperType started. Hold Ctrl+Shift+Z to record.")
    print("Press Ctrl+Shift+X to quit.")
    client = WhisperType()
    
    # Create system tray icon
    indicator = WhisperTypeIndicator(client)
    
    # Update status every second
    GLib.timeout_add(1000, indicator.update_status)
    
    # Check server status every 5 seconds
    GLib.timeout_add(5000, indicator.check_server)
    
    try:
        # Run the GTK main loop
        Gtk.main()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        client.running = False

if __name__ == "__main__":
    main() 