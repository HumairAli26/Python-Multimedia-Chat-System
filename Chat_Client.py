"""
Simplified Chat Client (Non-Tabbed, Classic Layout)

- FIX: Voice Message recording logic updated to correctly handle PyAudio resources (wave file creation).
- FIX: Group Chat/File messages will be received by all clients (relying on server broadcast fix).
- NEW: Voice Message recording and sending functionality added.
- Contextual UI for calls is maintained.
"""

import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, simpledialog
import base64
import os
from datetime import datetime
import cv2
import pyaudio
from PIL import Image, ImageTk
import io
import queue
import time
import sys
import wave

# Media settings (Standard performance)
VIDEO_WIDTH = 320
VIDEO_HEIGHT = 240
VIDEO_QUALITY = 30
VIDEO_FPS_DELAY = 0.05
AUDIO_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHUNK = 1024

# --- Theme Constants (Modern Dark Theme) ---
BG_MAIN = "#1c1c1c"  # Dark Charcoal (Main background)
BG_CHAT = "#252526"  # Slightly Lighter Charcoal (Chat/List backgrounds)
BG_SIDE = "#202020"  # Medium Charcoal (Sidebar background)
FG_TEXT = "#e0e0e0"  # Light Grey (Primary text)
ACCENT_BLUE = '#007ACC'  # VS Code Blue (Accent)
ACCENT_GREEN = '#60A917' # Modern Green (Send/Connect)
ACCENT_RED = '#E74856'  # Modern Red (End Call)
ACCENT_PURPLE = '#A200FF' # Purple for Private Chat
FONT_MAIN = ('Segoe UI', 10)
FONT_BOLD = ('Segoe UI', 10, 'bold')
ICON_SIZE = 18 # For simplified button sizing

class SimplifiedClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Simplified Chat Terminal")
        self.root.geometry("900x600")
        self.root.configure(bg=BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Network
        self.socket = None
        self.username = None
        self.connected = False

        # UI / state
        self.current_room = 'General'
        self.private_chat_user = None
        self.chat_ui_ready = False
        self.message_queue = []

        # History storage
        self.group_history = {}
        self.private_history = {}

        # Media / call state
        self.in_call = False
        self.call_peer = None 
        self.call_type = None
        self.is_group_call = False

        # --- Voice Message Recording State ---
        self.is_recording = False
        self.audio_frames = []
        self.temp_audio_file = os.path.join(os.path.expanduser('~'), 'temp_voice_msg.wav')
        self.rec_interface = None
        self.rec_stream = None
        self.rec_thread = None

        # UI elements to be defined later
        self.private_voice_btn = None
        self.private_video_btn = None
        self.group_voice_btn = None
        self.group_video_btn = None
        self.end_call_btn = None
        self.voice_msg_btn = None


        # Media handlers (for real-time call)
        self.video_capture = None
        self.video_send_thread = None
        self.video_display_thread = None
        self.video_display_queue = queue.Queue(maxsize=8)
        self.audio_interface = None
        self.audio_stream_in = None
        self.audio_stream_out = None
        self.audio_send_thread = None
        self.audio_play_queue = queue.Queue(maxsize=50)
        self.call_stop_event = threading.Event()

        # Downloads
        self.download_folder = os.path.join(os.path.expanduser('~'), 'ChatDownloads_Simplified')
        os.makedirs(self.download_folder, exist_ok=True)

        # Build UI
        self.setup_login_ui()

    # ---------------- UI Setup ----------------
    def setup_login_ui(self):
        self.login_frame = tk.Frame(self.root, bg=BG_MAIN)
        self.login_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(self.login_frame, text="Secure Chat Client Login", font=('Segoe UI', 20, 'bold'), bg=BG_MAIN, fg=ACCENT_BLUE).pack(pady=50) 
        
        tk.Label(self.login_frame, text="Server Host:", bg=BG_MAIN, fg=FG_TEXT, font=FONT_MAIN).pack(pady=4)
        self.host_entry = tk.Entry(self.login_frame, font=FONT_MAIN, width=30, bg=BG_CHAT, fg=FG_TEXT, insertbackground=FG_TEXT, relief=tk.FLAT)
        self.host_entry.insert(0, '127.0.0.1')
        self.host_entry.pack(pady=4)

        tk.Label(self.login_frame, text="Server Port:", bg=BG_MAIN, fg=FG_TEXT, font=FONT_MAIN).pack(pady=4)
        self.port_entry = tk.Entry(self.login_frame, font=FONT_MAIN, width=30, bg=BG_CHAT, fg=FG_TEXT, insertbackground=FG_TEXT, relief=tk.FLAT)
        self.port_entry.insert(0, '5555')
        self.port_entry.pack(pady=4)
        
        tk.Label(self.login_frame, text="Username:", bg=BG_MAIN, fg=FG_TEXT, font=FONT_MAIN).pack(pady=4)
        self.username_entry = tk.Entry(self.login_frame, font=FONT_MAIN, width=30, bg=BG_CHAT, fg=FG_TEXT, insertbackground=FG_TEXT, relief=tk.FLAT)
        self.username_entry.pack(pady=4)
        self.username_entry.bind('<Return>', lambda e: self.connect())
        
        self.connect_btn = tk.Button(self.login_frame, text="🔗 Connect", font=('Segoe UI', 12, 'bold'), bg=ACCENT_GREEN, fg=BG_MAIN, width=15, command=self.connect, relief=tk.FLAT)
        self.connect_btn.pack(pady=25)
        self.status_label = tk.Label(self.login_frame, text="", bg=BG_MAIN, fg=ACCENT_RED, font=FONT_MAIN)
        self.status_label.pack(pady=6)

    def setup_chat_ui(self):
        main_frame = tk.Frame(self.root, bg=BG_MAIN)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left Sidebar (Users & Rooms)
        left_frame = tk.Frame(main_frame, width=220, bg=BG_SIDE, relief=tk.FLAT) 
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)

        tk.Label(left_frame, text=f"👤 Logged in as: {self.username}", bg=BG_SIDE, fg=ACCENT_GREEN, font=('Segoe UI', 11, 'bold')).pack(pady=10)
        
        # Online Users
        tk.Label(left_frame, text="🟢 Online Users (Double-click for Chat)", bg=BG_SIDE, fg=FG_TEXT, font=FONT_BOLD).pack(pady=(10, 5))
        self.users_listbox = tk.Listbox(left_frame, bg=BG_CHAT, fg=FG_TEXT, selectbackground=ACCENT_PURPLE, font=FONT_MAIN, height=8, relief=tk.FLAT)
        self.users_listbox.pack(fill=tk.X, padx=8)
        self.users_listbox.bind('<Double-Button-1>', self.start_private_chat)
        
        # Chat Rooms
        tk.Label(left_frame, text="🏢 Chat Rooms (Click to Enter)", bg=BG_SIDE, fg=FG_TEXT, font=FONT_BOLD).pack(pady=(10, 5))
        self.rooms_listbox = tk.Listbox(left_frame, bg=BG_CHAT, fg=FG_TEXT, selectbackground=ACCENT_BLUE, font=FONT_MAIN, height=6, relief=tk.FLAT)
        self.rooms_listbox.pack(fill=tk.X, padx=8)
        self.rooms_listbox.insert(tk.END, "General")
        self.rooms_listbox.bind('<<ListboxSelect>>', self.switch_room)
        
        room_btn_frame = tk.Frame(left_frame, bg=BG_SIDE)
        room_btn_frame.pack(pady=6)
        tk.Button(room_btn_frame, text="➕ Create Room", command=self.create_room, bg=ACCENT_GREEN, fg=BG_CHAT, width=12, relief=tk.FLAT).pack(side=tk.LEFT, padx=3)

        # Right Area (Chat & Input)
        right_frame = tk.Frame(main_frame, bg=BG_CHAT)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Chat Header Frame (For Header and Call Buttons) ---
        header_frame = tk.Frame(right_frame, bg=ACCENT_BLUE, height=40)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        self.chat_header = tk.Label(header_frame, text=f"Room: {self.current_room}", bg=ACCENT_BLUE, fg=BG_CHAT, font=('Segoe UI', 12, 'bold'))
        self.chat_header.pack(side=tk.LEFT, padx=10)

        # Call Buttons Frame (Top Right)
        self.call_btns_frame = tk.Frame(header_frame, bg=ACCENT_BLUE)
        self.call_btns_frame.pack(side=tk.RIGHT, padx=5)

        # Call Buttons Configuration
        btn_config = {'fg':BG_MAIN, 'font':('Segoe UI', 10, 'bold'), 'width':ICON_SIZE//5, 'height':ICON_SIZE//10, 'relief':tk.FLAT}

        # Private Call Buttons (Voice/Video)
        self.private_voice_btn = tk.Button(self.call_btns_frame, text="📞", command=lambda: self.initiate_call('private', 'voice'), **btn_config, bg='#f39c12')
        self.private_video_btn = tk.Button(self.call_btns_frame, text="📹", command=lambda: self.initiate_call('private', 'video'), **btn_config, bg='#8e44ad')

        # Group Call Buttons (Voice/Video)
        self.group_voice_btn = tk.Button(self.call_btns_frame, text="📞", command=lambda: self.initiate_call('group', 'voice'), **btn_config, bg='#f39c12')
        self.group_video_btn = tk.Button(self.call_btns_frame, text="📹", command=lambda: self.initiate_call('group', 'video'), **btn_config, bg=ACCENT_PURPLE)
        
        # End Call Button 
        self.end_call_btn = tk.Button(self.call_btns_frame, text="🛑", command=self.end_call, **btn_config, bg=ACCENT_RED)


        self.chat_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=FONT_MAIN, state=tk.DISABLED, bg=BG_MAIN, fg=FG_TEXT, relief=tk.FLAT, bd=0)
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.chat_display.tag_config('time', foreground='#777777')
        self.chat_display.tag_config('sender', foreground=ACCENT_BLUE, font=FONT_BOLD)
        self.chat_display.tag_config('system', foreground=ACCENT_RED)
        self.chat_display.tag_config('private', foreground=ACCENT_PURPLE)

        # Input Frame (Contains Mic, Text Entry, and Send/File Buttons)
        input_controls_frame = tk.Frame(right_frame, bg=BG_CHAT)
        input_controls_frame.pack(fill=tk.X, padx=8, pady=8)
        
        # --- Voice Message Button (Microphone Symbol) ---
        self.voice_msg_btn = tk.Button(input_controls_frame, text="🎤", command=self.toggle_recording, 
                                       bg=ACCENT_BLUE, fg=BG_MAIN, font=('Segoe UI', 12, 'bold'), 
                                       width=3, height=2, relief=tk.FLAT)
        self.voice_msg_btn.pack(side=tk.LEFT, padx=(0, 6), fill=tk.Y)


        self.message_entry = tk.Text(input_controls_frame, height=3, font=FONT_MAIN, relief=tk.FLAT, bd=1, bg=BG_MAIN, fg=FG_TEXT, insertbackground=FG_TEXT)
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.message_entry.bind('<Return>', self.send_message)
        self.message_entry.bind('<Shift-Return>', lambda e: None)

        button_frame = tk.Frame(input_controls_frame, bg=BG_CHAT)
        button_frame.pack(side=tk.LEFT, padx=6)
        
        # Action Buttons (Send and File)
        tk.Button(button_frame, text="📧 Send", command=self.send_message, bg=ACCENT_GREEN, fg=BG_CHAT, width=10, relief=tk.FLAT).pack(pady=2)
        tk.Button(button_frame, text="📁 File", command=self.send_file, bg=ACCENT_BLUE, fg=BG_CHAT, width=10, relief=tk.FLAT).pack(pady=2)

        # Mark UI ready
        self.chat_ui_ready = True
        self.root.after(100, self.process_queued_messages)
        
        # Default to 'General' room selection and update buttons
        self.rooms_listbox.selection_set(0) 
        self.rooms_listbox.event_generate("<<ListboxSelect>>")
        
    def update_call_buttons(self):
        """Hides or shows the appropriate call buttons based on the current chat context."""
        
        # Hide all call buttons first
        self.private_voice_btn.pack_forget()
        self.private_video_btn.pack_forget()
        self.group_voice_btn.pack_forget()
        self.group_video_btn.pack_forget()
        self.end_call_btn.pack_forget()
        
        # Disable voice message button while in a real-time call
        if self.voice_msg_btn:
            self.voice_msg_btn.config(state=tk.DISABLED if self.in_call else tk.NORMAL)


        if self.in_call:
            # If in call, only show the end call button
            self.end_call_btn.pack(side=tk.RIGHT, padx=5)
        elif self.private_chat_user:
            # Private chat context
            self.private_video_btn.pack(side=tk.RIGHT, padx=5)
            self.private_voice_btn.pack(side=tk.RIGHT, padx=5)
        elif self.current_room:
            # Group chat context (Room)
            self.group_video_btn.pack(side=tk.RIGHT, padx=5)
            self.group_voice_btn.pack(side=tk.RIGHT, padx=5)

    # ---------------- Voice Message Recording Logic (FIXED) ----------------
    def toggle_recording(self):
        if self.in_call:
            messagebox.showwarning("Busy", "Cannot record voice message while in a real-time call.")
            return

        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        self.is_recording = True
        self.audio_frames = []
        
        # Update UI to indicate recording
        self.voice_msg_btn.config(text="🔴", bg=ACCENT_RED, fg=BG_MAIN)
        self.display_system_message("Recording voice message... Click again to stop and send.")
        
        try:
            self.rec_interface = pyaudio.PyAudio()
            self.rec_stream = self.rec_interface.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK,
                stream_callback=self._audio_callback
            )
            
            self.rec_stream.start_stream()
            self.rec_thread = threading.Thread(target=self._recording_loop, daemon=True)
            self.rec_thread.start()

        except Exception as e:
            self.is_recording = False
            self.voice_msg_btn.config(text="🎤", bg=ACCENT_BLUE, fg=BG_MAIN)
            messagebox.showerror("Audio Error", f"Could not start recording: {e}")


    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function to append recorded audio data."""
        if self.is_recording:
            self.audio_frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def _recording_loop(self):
        """Simple loop to keep the recording thread alive until stop is called."""
        # Wait for the recording to be stopped or until thread is killed
        while self.is_recording:
            time.sleep(0.1)
        
        # Ensure cleanup and stream stop is called after is_recording is false
        if self.rec_stream and self.rec_stream.is_active():
            self.rec_stream.stop_stream()
            self.rec_stream.close()
        self.rec_stream = None


    def stop_recording(self):
        if not self.is_recording: return
        self.is_recording = False
        
        self.voice_msg_btn.config(text="🎤", bg=ACCENT_BLUE, fg=BG_MAIN)
        self.display_system_message("Voice message stopped. Preparing to send...")

        # Wait for the recording loop to finish cleanup
        if self.rec_thread:
            self.rec_thread.join(timeout=1.0) 
            self.rec_thread = None

        if not self.audio_frames:
            self.display_system_message("Recording too short or failed.")
            if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
            return

        # 1. Save frames to WAV file (FIX: Must get sample size before terminating interface)
        try:
            # Use self.rec_interface to get sample size
            sample_width = self.rec_interface.get_sample_size(AUDIO_FORMAT)

            with wave.open(self.temp_audio_file, 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(sample_width) # Use calculated width
                wf.setframerate(AUDIO_RATE)
                wf.writeframes(b''.join(self.audio_frames))
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save audio file: {e}")
            if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
            return
        
        # 2. Send the WAV file using the existing file transfer mechanism
        self._send_voice_message_file(self.temp_audio_file)
        
        # 3. Cleanup: Terminate interface and delete temp file
        if self.rec_interface: self.rec_interface.terminate(); self.rec_interface = None
        try: os.remove(self.temp_audio_file)
        except: pass

    def _send_voice_message_file(self, filepath):
        """Sends the recorded WAV file."""
        try:
            # File size check (same as regular file send)
            file_size = os.path.getsize(filepath)
            if file_size > 20 * 1024 * 1024:
                messagebox.showerror("Error", "Voice message file size must be <20MB")
                return
                
            with open(filepath, 'rb') as f:
                filedata = base64.b64encode(f.read()).decode('utf-8')
            
            # Use a distinctive name and type for voice messages
            filename = f"voice_msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            filetype = '.wav'
            
            data = {'type':'file','filename':filename,'filedata':filedata,'filetype':filetype}
            
            if self.private_chat_user:
                data['recipient'] = self.private_chat_user
            else:
                data['room'] = self.current_room
                
            self._send_json(data)
            self.display_system_message("🎤 Voice message sent.")
            
        except Exception as e:
            messagebox.showerror("Send Error", f"Voice message send failed: {e}")

    # ---------------- Networking / framing ----------------
    def connect(self):
        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()
        username = self.username_entry.get().strip()
        if not username:
            self.status_label.config(text="Please enter a username")
            return
        try:
            port = int(port)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.socket.send(username.encode('utf-8'))
            self.username = username
            self.connected = True
            self.login_frame.destroy()
            self.setup_chat_ui()
            recv_thread = threading.Thread(target=self.receive_messages, daemon=True)
            recv_thread.start()
        except Exception as e:
            self.status_label.config(text=f"Connection failed: {e}")

    def _send_json(self, data):
        try:
            payload = json.dumps(data) + "\n"
            self.socket.send(payload.encode('utf-8'))
        except Exception as e:
            print("Send JSON error:", e)

    def receive_messages(self):
        buffer = ""
        decoder = json.JSONDecoder()
        try:
            while self.connected:
                try:
                    data = self.socket.recv(1024 * 1024 * 4)
                    if not data:
                        break
                    buffer += data.decode('utf-8', errors='ignore')
                    while buffer:
                        buffer = buffer.lstrip()
                        try:
                            obj, idx = decoder.raw_decode(buffer)
                            buffer = buffer[idx:]
                            self.process_message(obj)
                        except ValueError:
                            break
                except Exception as e:
                    print("Receiver error:", e)
                    break
        finally:
            self.connected = False

    # ---------------- Message processing ----------------
    def process_message(self, message):
        if not self.chat_ui_ready:
            self.message_queue.append(message)
            return

        msg_type = message.get('type')
        if msg_type == 'welcome':
            self.display_system_message(message.get('message'))
            for room in message.get('rooms', []):
                if room not in self.rooms_listbox.get(0, tk.END):
                    self.rooms_listbox.insert(tk.END, room)
        elif msg_type == 'chat':
            room = message.get('room')
            sender = message.get('sender')
            msg = message.get('message')
            ts = message.get('timestamp') or datetime.now().strftime('%H:%M:%S')
            self.group_history.setdefault(room, []).append((ts, sender, msg))
            if room == self.current_room and not self.private_chat_user:
                self.display_message(sender, msg, ts)
        elif msg_type == 'private':
            sender = message.get('sender')
            msg = message.get('message')
            ts = message.get('timestamp') or datetime.now().strftime('%H:%M:%S')
            self.private_history.setdefault(sender, []).append((ts, sender, msg))
            if self.private_chat_user == sender:
                self.display_private_message(sender, msg, ts)
            else:
                self.display_system_message(f"🔒 New private message from {sender}")
        elif msg_type == 'file':
            sender = message.get('sender')
            filename = message.get('filename')
            filedata = message.get('filedata')
            ts = message.get('timestamp') or datetime.now().strftime('%H:%M:%S')
            self.receive_file(sender, filename, filedata, message.get('filetype'), ts)
        elif msg_type == 'client_list':
            self.update_user_list(message.get('clients', []))
        elif msg_type == 'room_created':
            room = message.get('room_name')
            if room not in self.rooms_listbox.get(0, tk.END):
                self.rooms_listbox.insert(tk.END, room)
            self.display_system_message(f"Room '{room}' created")
        
        # --- Call Signaling ---
        elif msg_type == 'call_request':
            caller = message.get('caller')
            call_type = message.get('call_type')
            self.handle_call_request(caller, call_type)
        elif msg_type == 'group_call_request':
            room = message.get('room')
            caller = message.get('caller')
            call_type = message.get('call_type')
            self.handle_group_call_request(room, caller, call_type)
        elif msg_type == 'call_response':
            responder = message.get('responder')
            accepted = message.get('accepted')
            call_type = message.get('call_type', 'video')
            self.handle_call_response(responder, accepted, call_type)
        elif msg_type == 'call_data':
            sender = message.get('sender')
            if self.is_group_call and sender == self.username: # Ignore own data in group call
                return
            data_type = message.get('data_type')
            data_b64 = message.get('data')
            
            if data_type == 'video':
                try:
                    frame_bytes = base64.b64decode(data_b64)
                    try: self.video_display_queue.put_nowait(frame_bytes)
                    except queue.Full: pass
                except Exception as e:
                    print("Video decode error:", e)
            elif data_type == 'audio':
                try:
                    audio_bytes = base64.b64decode(data_b64)
                    try: self.audio_play_queue.put_nowait(audio_bytes)
                    except queue.Full: pass
                except Exception as e:
                    print("Audio decode error:", e)
        elif msg_type == 'call_ended':
            peer = message.get('peer')
            self.display_system_message(f"Call with {peer} ended")
            self._stop_call_internal()

    def process_queued_messages(self):
        while self.message_queue:
            self.process_message(self.message_queue.pop(0))

    # ---------------- UI display helpers ----------------
    def display_message(self, sender, message, timestamp):
        if not self.chat_ui_ready: return
        def update():
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, f"[{timestamp}] ", 'time')
            self.chat_display.insert(tk.END, f"{sender}: ", 'sender')
            self.chat_display.insert(tk.END, f"{message}\n")
            self.chat_display.config(state=tk.DISABLED)
            self.chat_display.see(tk.END)
        self.root.after(0, update)

    def display_private_message(self, sender, message, timestamp):
        if not self.chat_ui_ready: return
        def update():
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, f"[{timestamp}] ", 'time')
            self.chat_display.insert(tk.END, f"🔒 {sender}: ", 'private')
            self.chat_display.insert(tk.END, f"{message}\n")
            self.chat_display.config(state=tk.DISABLED)
            self.chat_display.see(tk.END)
        self.root.after(0, update)

    def display_system_message(self, message):
        if not self.chat_ui_ready: return
        def update():
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.insert(tk.END, f"[SYSTEM] {message}\n", 'system')
            self.chat_display.config(state=tk.DISABLED)
            self.chat_display.see(tk.END)
        self.root.after(0, update)

    # ---------------- Sending messages (Same as Original) ----------------
    def send_message(self, event=None):
        message = self.message_entry.get('1.0', tk.END).strip()
        if not message: return 'break' if event else None
        if event and event.state & 0x1: return
        ts = datetime.now().strftime('%H:%M:%S')
        try:
            if self.private_chat_user:
                data = {'type':'private','recipient':self.private_chat_user,'message':message}
                self._send_json(data)
                self.private_history.setdefault(self.private_chat_user, []).append((ts, self.username, message))
                self.display_private_message(self.username, message, ts)
            else:
                data = {'type':'chat','room':self.current_room,'message':message}
                self._send_json(data)
                self.group_history.setdefault(self.current_room, []).append((ts, self.username, message))
                self.display_message(self.username, message, ts)
            self.message_entry.delete('1.0', tk.END)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send: {e}")
        return 'break' if event else None

    # ---------------- File transfer & Voice Message Reception (FIXED) ----------------
    def send_file(self):
        filepath = filedialog.askopenfilename(title="Select file to send")
        if not filepath: return
        try:
            file_size = os.path.getsize(filepath)
            if file_size > 20 * 1024 * 1024:
                messagebox.showerror("Error", "File size must be <20MB")
                return
            with open(filepath, 'rb') as f:
                filedata = base64.b64encode(f.read()).decode('utf-8')
            filename = os.path.basename(filepath)
            filetype = os.path.splitext(filename)[1].lower()
            data = {'type':'file','filename':filename,'filedata':filedata,'filetype':filetype}
            if self.private_chat_user:
                data['recipient'] = self.private_chat_user
            else:
                data['room'] = self.current_room
            self._send_json(data)
            self.display_system_message(f"File '{filename}' sent")
        except Exception as e:
            messagebox.showerror("Error", f"File send failed: {e}")

    def receive_file(self, sender, filename, filedata, filetype, timestamp):
        try:
            file_bytes = base64.b64decode(filedata)
            
            is_voice_msg = (filetype == '.wav' and filename.startswith('voice_msg_'))

            save_path = os.path.join(self.download_folder, filename)
            counter = 1
            while os.path.exists(save_path):
                name, ext = os.path.splitext(filename)
                save_path = os.path.join(self.download_folder, f"{name}_{counter}{ext}")
                counter += 1
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
            
            if is_voice_msg:
                self.display_system_message(f"🎤 New Voice Message received from {sender}. Saved to download folder: {save_path}")
            else:
                self.display_system_message(f"File '{filename}' received from {sender} → {save_path}")
            
        except Exception as e:
            self.display_system_message(f"Error receiving file: {e}")

    # ---------------- User / room helpers ----------------
    def update_user_list(self, users):
        if not self.chat_ui_ready: return
        def update():
            self.users_listbox.delete(0, tk.END)
            for u in users:
                if u != self.username:
                    self.users_listbox.insert(tk.END, u)
        self.root.after(0, update)

    def start_private_chat(self, event=None):
        if event:
            try:
                selection = self.users_listbox.curselection()
                if not selection: return
                user = self.users_listbox.get(selection[0])
            except Exception: return
        else:
            return 

        self.current_room = None
        self.private_chat_user = user
        self.chat_header.config(text=f"🔒 Private Chat: {user}", bg=ACCENT_PURPLE)
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete('1.0', tk.END)
        hist = self.private_history.get(user, [])
        for ts, sender, msg in hist:
            self.display_private_message(sender if sender != self.username else 'You', msg, ts)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        self.display_system_message(f"Private chat with {user} started")
        
        self.update_call_buttons()

    def switch_room(self, event):
        selection = self.rooms_listbox.curselection()
        if not selection: return
        room = self.rooms_listbox.get(selection[0])
        self.current_room = room
        self.private_chat_user = None
        self.chat_header.config(text=f"Room: {room}", bg=ACCENT_BLUE)
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete('1.0', tk.END)
        hist = self.group_history.get(room, [])
        for ts, sender, msg in hist:
            self.display_message(sender, msg, ts)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        self.display_system_message(f"Switched to room: {room}")

        self.update_call_buttons()

    def create_room(self):
        room_name = simpledialog.askstring("Create Room", "Enter room name:")
        if room_name:
            data = {'type':'create_room','room_name':room_name}
            self._send_json(data)

    # ---------------- Calling ----------------
    def initiate_call(self, target_type, call_type):
        if self.in_call:
            messagebox.showwarning("Warning", "Already in an active call.")
            return

        if target_type == 'private':
            if not self.private_chat_user:
                messagebox.showinfo("Info", "Please double-click a user in the list to start a private chat/call.")
                return

            recipient = self.private_chat_user
            data = {'type':'call_request','recipient':recipient,'call_type':call_type}
            self._send_json(data)
            self.call_peer = recipient
            self.is_group_call = False
            self.display_system_message(f"Calling {recipient}... ({call_type})")
        
        elif target_type == 'group':
            room = self.current_room
            if not room:
                messagebox.showinfo("Info", "Please select a room to start a group call.")
                return

            data = {'type':'group_call_request','room':room,'caller':self.username,'call_type':call_type}
            self._send_json(data)
            self.call_peer = room
            self.is_group_call = True
            self.display_system_message(f"Initiating Group Call in {room} ({call_type})...")
            self._start_call_internal(room, call_type, is_group=True)
        
        self.update_call_buttons()


    def handle_call_request(self, caller, call_type):
        if self.in_call:
            data = {'type':'call_response','caller':caller,'accepted':False,'call_type':call_type}
            self._send_json(data)
            return
        response = messagebox.askyesno("Incoming Call", f"{caller} is calling you ({call_type}). Accept?")
        data = {'type':'call_response','caller':caller,'accepted':response,'call_type':call_type}
        self._send_json(data)
        if response:
            self.call_peer = caller
            self.is_group_call = False
            self.root.after(200, lambda: self._start_call_internal(caller, call_type, is_group=False))
        
        self.update_call_buttons()

    def handle_group_call_request(self, room, caller, call_type):
        if self.in_call or caller == self.username:
            return 

        response = messagebox.askyesno("Incoming Group Call", f"{caller} started a {call_type} call in room '{room}'. Join?")
        if response:
            self.display_system_message(f"Joining active Group Call in room {room} ({call_type}).")
            self.call_peer = room
            self.is_group_call = True
            self.root.after(200, lambda: self._start_call_internal(room, call_type, is_group=True))
        
        self.update_call_buttons()

    def handle_call_response(self, responder, accepted, call_type):
        if accepted:
            self.display_system_message(f"{responder} accepted the call")
            self.call_peer = responder
            self.is_group_call = False
            self._start_call_internal(responder, call_type, is_group=False)
        else:
            self.display_system_message(f"{responder} rejected the call")
        
        self.update_call_buttons()


    def end_call(self):
        if not self.in_call: return

        if self.is_group_call:
            data = {'type':'end_call', 'is_group': True, 'room': self.call_peer}
            self._send_json(data)
        else:
            data = {'type':'end_call', 'is_group': False}
            self._send_json(data)

        self._stop_call_internal()
        self.display_system_message("You ended the call")
        self.update_call_buttons() # Reset buttons based on current chat context

    def _start_call_internal(self, peer, call_type, is_group):
        if self.in_call: return
        self.in_call = True
        self.call_peer = peer
        self.call_type = call_type
        self.is_group_call = is_group
        self.call_stop_event.clear()

        # Audio setup
        if call_type in ('voice', 'video', 'both'):
            try:
                self.audio_interface = pyaudio.PyAudio()
                self.audio_stream_in = self.audio_interface.open(format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True, frames_per_buffer=AUDIO_CHUNK)
                self.audio_stream_out = self.audio_interface.open(format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, output=True, frames_per_buffer=AUDIO_CHUNK)
                if self.audio_stream_in:
                    self.audio_send_thread = threading.Thread(target=self._audio_send_loop, daemon=True)
                    self.audio_send_thread.start()
                if self.audio_stream_out:
                    self.audio_play_thread = threading.Thread(target=self._audio_play_loop, daemon=True)
                    self.audio_play_thread.start()
            except Exception as e:
                print("Audio init error:", e)

        # Video setup
        if call_type in ('video', 'both'):
            try:
                self.video_capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, VIDEO_WIDTH)
                self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, VIDEO_HEIGHT)
            except Exception as e:
                print("Video capture init error:", e)
                self.video_capture = None

            if self.video_capture and self.video_capture.isOpened():
                self.video_send_thread = threading.Thread(target=self._video_send_loop, daemon=True)
                self.video_send_thread.start()
                self.video_display_thread = threading.Thread(target=self._video_display_loop, daemon=True)
                self.video_display_thread.start()
            else:
                print("Camera not available")

        self._open_call_window()
        self.update_call_buttons() # Update buttons to show End Call

    def _stop_call_internal(self):
        self.call_stop_event.set()
        self.in_call = False
        self.call_peer = None
        self.call_type = None
        self.is_group_call = False 

        try:
            if self.video_capture: self.video_capture.release()
            if self.audio_stream_in: self.audio_stream_in.stop_stream(); self.audio_stream_in.close()
            if self.audio_stream_out: self.audio_stream_out.stop_stream(); self.audio_stream_out.close()
            if self.audio_interface: self.audio_interface.terminate()
        except: pass
        with self.video_display_queue.mutex: self.video_display_queue.queue.clear()
        with self.audio_play_queue.mutex: self.audio_play_queue.queue.clear()
        try:
            if hasattr(self, 'call_window') and self.call_window:
                if self.call_window.winfo_exists(): self.call_window.destroy()
                self.call_window = None
        except: pass

    # ---------------- Media loops ----------------
    def _video_send_loop(self):
        while not self.call_stop_event.is_set() and self.video_capture and self.video_capture.isOpened():
            ret, frame = self.video_capture.read()
            if not ret: time.sleep(0.02); continue
            frame = cv2.resize(frame, (VIDEO_WIDTH, VIDEO_HEIGHT))
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), VIDEO_QUALITY]
            ok, encoded = cv2.imencode('.jpg', frame, encode_param)
            if not ok: continue
            bts = encoded.tobytes()
            b64 = base64.b64encode(bts).decode('utf-8')
            
            payload = {'type':'call_data','data':b64,'data_type':'video','sender':self.username}
            if self.is_group_call:
                payload['room'] = self.call_peer
            else:
                payload['peer'] = self.call_peer
            
            try:
                self._send_json(payload)
            except Exception as e:
                print("Video send error:", e)
                break
            time.sleep(VIDEO_FPS_DELAY)

    def _audio_send_loop(self):
        while not self.call_stop_event.is_set():
            if not self.audio_stream_in: time.sleep(0.02); continue
            try:
                data = self.audio_stream_in.read(AUDIO_CHUNK, exception_on_overflow=False)
                if not data: continue
                b64 = base64.b64encode(data).decode('utf-8')
                
                payload = {'type':'call_data','data':b64,'data_type':'audio','sender':self.username}
                if self.is_group_call:
                    payload['room'] = self.call_peer
                else:
                    payload['peer'] = self.call_peer

                self._send_json(payload)
            except Exception as e:
                print("Audio send error:", e)
                break

    def _audio_play_loop(self):
        while not self.call_stop_event.is_set():
            try:
                audio_bytes = self.audio_play_queue.get(timeout=0.5)
            except queue.Empty: continue
            if self.audio_stream_out:
                try:
                    self.audio_stream_out.write(audio_bytes, exception_on_underflow=False)
                except Exception: pass

    def _video_display_loop(self):
        while not self.call_stop_event.is_set():
            try:
                frame_bytes = self.video_display_queue.get(timeout=0.5)
            except queue.Empty: continue
            try:
                image = Image.open(io.BytesIO(frame_bytes))
                image_tk = ImageTk.PhotoImage(image)
            except Exception as e:
                print("Display frame decode error:", e)
                continue

            def updater():
                try:
                    if not self.in_call or not hasattr(self, 'call_video_label') or not self.call_video_label.winfo_exists(): return
                    self.call_video_label.configure(image=image_tk)
                    self.call_video_label.image = image_tk
                except Exception: pass
            try: self.root.after(0, updater)
            except Exception: pass

    # ---------------- Call window (Simplified) ----------------
    def _open_call_window(self):
        try:
            peer_info = self.call_peer
            if self.is_group_call:
                peer_info = f"Group: {self.call_peer}"

            self.call_window = tk.Toplevel(self.root)
            self.call_window.title(f"Active Call: {peer_info}")
            self.call_window.configure(bg=BG_SIDE)
            
            call_label = tk.Label(self.call_window, text=f"Call Target: {peer_info} ({self.call_type.upper()})", font=FONT_BOLD, bg=BG_SIDE, fg=ACCENT_BLUE)
            call_label.pack(pady=5)

            if self.call_type in ('video', 'both'):
                self.call_window.geometry("340x280")
                self.call_video_label = tk.Label(self.call_window, bg='black', text="Video Stream Active", fg='white')
                self.call_video_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            else:
                self.call_window.geometry("300x100")
                self.call_video_label = None
                tk.Label(self.call_window, text="Audio Call Active (No Video Stream)", font=FONT_MAIN, bg=BG_SIDE, fg=FG_TEXT).pack(pady=10)

            def on_close(): self.end_call()
            self.call_window.protocol("WM_DELETE_WINDOW", on_close)
        except Exception as e:
            print("Call window error:", e)

    # ---------------- Cleanup (Same as Original) ----------------
    def on_closing(self):
        try:
            if self.in_call: self.end_call()
            # Stop recording if active
            if self.is_recording: self.is_recording = False
            
            if self.connected:
                try: self.socket.close()
                except: pass
        except: pass
        self.root.destroy()

# ----------------- Run client -----------------
if __name__ == '__main__':
    root = tk.Tk()
    app = SimplifiedClient(root)
    root.mainloop()