import socket
import threading
import json
import base64
import os
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
import cv2
import random

# ---------------------------
# CONFIGURATION
# ---------------------------
DEFAULT_HOST = "10.75.6.12" # Change this to your Server's IP address!
DEFAULT_TCP_PORT = 9009 
DEFAULT_UDP_PORT = 9010 # Server's fixed UDP port (must match server)
AUDIO_FS = 16000

# --- DARK MODE CONSTANTS ---
BG_COLOR = "#1e1e1e"        # Dark Gray Background
SIDEBAR_BG = "#2d2d30"      # Slightly Darker Sidebar
CHAT_BG = "#252526"         # Chat Log background
FG_COLOR = "#ffffff"        # White Foreground Text
ACCENT_COLOR = "#5c91ff"    # Light Blue/Accent (Primary)
ERROR_COLOR = "#ff5c5c"     # Red for errors/stops
SUCCESS_COLOR = "#57c757"   # Green for success/start
# ---------------------------

class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Multimedia Chat Client (Auto-Answer)")
        self.root.geometry("1000x700")
        self.root.config(bg=BG_COLOR)
        self.root.style = ttk.Style()
        self.root.style.theme_use('clam')

        # --- State Variables ---
        self.tcp_sock = None
        self.udp_sock = None
        self.server_udp_addr = (DEFAULT_HOST, DEFAULT_UDP_PORT)
        self.local_udp_port = random.randint(10000, 60000)
        self.username = ""
        self.is_connected = False
        self.stop_streaming = False
        self.file_buffer = {}
        
        # Audio/Video state
        self.audio_stream_active = False
        self.video_stream_active = False
        
        # Call Handshake State
        self.call_lock = threading.Lock()
        # 'idle', 'requesting', 'ringing', 'accepted', 'rejected'
        self.call_state = tk.StringVar(value='idle') 
        self.call_mode = None                       # 'audio' or 'video'
        self.current_call_target = None             # The user/room that initiated or is being called
        self.call_response_event = threading.Event() # For sender to wait for acceptance/rejection
        self.remote_udp_port = None                 # The port of the other user/server proxy
        
        self._apply_global_styles()
        self._init_login_screen()

    # -------------------------------------------------------
    # STYLING 
    # -------------------------------------------------------
    def _apply_global_styles(self):
        base_font = ("Arial", 11) 
        large_font = ("Arial", 14, 'bold')
        
        # Base Styles
        self.root.style.configure('.', font=base_font, background=BG_COLOR, foreground=FG_COLOR)
        self.root.style.configure('TFrame', background=BG_COLOR)
        self.root.style.configure('TLabel', font=base_font, background=BG_COLOR, foreground=FG_COLOR)
        self.root.style.configure('TEntry', font=base_font, fieldbackground="#3c3c3c", foreground=FG_COLOR, borderwidth=1)
        self.root.style.configure('TRadiobutton', font=base_font, background=SIDEBAR_BG, foreground=FG_COLOR)
        self.root.style.configure('TCheckbutton', font=base_font, background=SIDEBAR_BG, foreground=FG_COLOR) 

        # General Button (Dark Gray/Utility) - Reduced padding
        self.root.style.configure('TButton', font=base_font, padding=4, background='#505050', foreground=FG_COLOR)
        self.root.style.map('TButton',
            background=[('active', '#606060')],
            foreground=[('active', FG_COLOR)])

        # Login Screen
        self.root.style.configure('Title.TLabel', font=large_font, foreground=ACCENT_COLOR, background=BG_COLOR)
        self.root.style.configure('Connect.TButton', font=large_font, background=SUCCESS_COLOR, foreground='black')
        self.root.style.map('Connect.TButton',
            background=[('active', '#3e8f3e')],
            foreground=[('active', 'white')])

        # Chat Screen Specifics
        self.root.style.configure('Sidebar.TFrame', background=SIDEBAR_BG)
        self.root.style.configure('Header.TFrame', background=BG_COLOR)

        # Message & Media Input Buttons
        self.root.style.configure('Send.TButton', background=ACCENT_COLOR, foreground='black', font=('Arial', 11, 'bold'))
        self.root.style.map('Send.TButton', background=[('active', '#4a70b8')])
        
        # Streaming Buttons (Clear Contrast)
        self.root.style.configure('Stream.TButton', font=('Arial', 11, 'bold'), padding=4)
        
        # Start Call (Green)
        self.root.style.configure('Start.TButton', background=SUCCESS_COLOR, foreground='black')
        self.root.style.map('Start.TButton', background=[('active', '#3e8f3e')])

        # Stop Call (Red)
        self.root.style.configure('Stop.TButton', background=ERROR_COLOR, foreground='white')
        self.root.style.map('Stop.TButton', background=[('active', '#b84a4a')])
        
    # -------------------------------------------------------
    # UI CONSTRUCTION 
    # -------------------------------------------------------
    def _init_login_screen(self):
        self.login_frame = ttk.Frame(self.root, padding="30", relief='raised', style='TFrame') 
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(self.login_frame, text="Multimedia Chat Login 💬", style='Title.TLabel').grid(row=0, column=0, columnspan=2, pady=(0, 20))

        ttk.Label(self.login_frame, text="Server IP:").grid(row=1, column=0, sticky="e", padx=10, pady=5)
        self.entry_ip = ttk.Entry(self.login_frame, width=20)
        self.entry_ip.insert(0, DEFAULT_HOST)
        self.entry_ip.grid(row=1, column=1, pady=5, padx=10)

        ttk.Label(self.login_frame, text="TCP Port:").grid(row=2, column=0, sticky="e", padx=10, pady=5)
        self.entry_port = ttk.Entry(self.login_frame, width=20)
        self.entry_port.insert(0, str(DEFAULT_TCP_PORT))
        self.entry_port.grid(row=2, column=1, pady=5, padx=10)

        ttk.Label(self.login_frame, text="Username:").grid(row=3, column=0, sticky="e", padx=10, pady=5)
        self.entry_user = ttk.Entry(self.login_frame, width=20)
        self.entry_user.grid(row=3, column=1, pady=5, padx=10)

        btn_connect = ttk.Button(self.login_frame, text="Connect to Server", command=self.connect_to_server, style='Connect.TButton')
        btn_connect.grid(row=4, column=0, columnspan=2, pady=20, sticky="we")

    def _init_chat_screen(self):
        self.login_frame.destroy()
        
        main_container = ttk.Frame(self.root, padding="5")
        main_container.pack(fill="both", expand=True)
        
        # Configure Grid Rows/Columns
        main_container.grid_rowconfigure(0, weight=0)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_rowconfigure(2, weight=0)
        main_container.grid_columnconfigure(0, weight=0)
        main_container.grid_columnconfigure(1, weight=1)

        # --- 0. Header Area (Status/Info) ---
        header_frame = ttk.Frame(main_container, style='Header.TFrame', padding="5")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        ttk.Label(header_frame, text=f"User: {self.username}", font=("Arial", 12, "bold"), foreground=ACCENT_COLOR).pack(side="left", padx=5)
        ttk.Label(header_frame, text=f"| TCP Port: {DEFAULT_TCP_PORT} | Server UDP: {DEFAULT_UDP_PORT} | Local UDP: {self.local_udp_port}", font=("Arial", 9), foreground="#a0a0a0").pack(side="right", padx=5)


        # --- 1. Sidebar (Controls) ---
        sidebar = ttk.Frame(main_container, width=250, padding="10", style='Sidebar.TFrame')
        sidebar.grid(row=1, column=0, sticky="ns", padx=(0, 5))
        sidebar.propagate(False)

        # Mode Selection
        ttk.Label(sidebar, text="--- MESSAGING MODE ---", font=("Arial", 10, "bold"), background=SIDEBAR_BG).pack(pady=(10,3), anchor="w")
        self.mode_var = tk.StringVar(value="PM") 
        
        modes = [("Broadcast (All)", "GLOBAL"), ("Private Message", "PM"), ("Room Message", "ROOM")]
        for text, val in modes:
            ttk.Radiobutton(sidebar, text=text, variable=self.mode_var, value=val, command=self._update_target_label, style='TRadiobutton').pack(fill="x", pady=1, anchor="w")

        self.target_label = ttk.Label(sidebar, text="Target Username:", font=("Arial", 10, "bold"), background=SIDEBAR_BG)
        self.target_label.pack(pady=(10,3), anchor="w")
        self.entry_target = ttk.Entry(sidebar, width=25)
        self.entry_target.pack(fill="x", pady=2)
        self.mode_var.trace_add("write", lambda *args: self._update_target_label())

        # Media Streaming
        ttk.Label(sidebar, text="--- LIVE STREAMING ---", font=("Arial", 10, "bold"), background=SIDEBAR_BG).pack(pady=(15,3), anchor="w")
        
        self.btn_call = ttk.Button(sidebar, text="Start Audio Call 🎤", style='Start.TButton', command=lambda: self.initiate_call('audio'))
        self.btn_call.pack(fill="x", pady=(3, 7))
        
        self.btn_vid = ttk.Button(sidebar, text="Start Video Call 📹", style='Start.TButton', command=lambda: self.initiate_call('video'))
        self.btn_vid.pack(fill="x", pady=3)
        
        self.btn_end_call = ttk.Button(sidebar, text="End Current Call 🛑", style='Stop.TButton', command=self.end_call)
        self.btn_end_call.pack(fill="x", pady=(10, 3))
        self.btn_end_call.config(state='disabled')


        # Room Controls
        ttk.Label(sidebar, text="--- ROOM MANAGEMENT ---", font=("Arial", 10, "bold"), background=SIDEBAR_BG).pack(pady=(15,3), anchor="w")
        ttk.Button(sidebar, text="➕ Create Room", command=self.create_room_dialog).pack(fill="x", pady=2)
        ttk.Button(sidebar, text="➡ Join Room", command=self.join_room_dialog).pack(fill="x", pady=2)
        ttk.Button(sidebar, text="⬅ Leave Room", command=self.leave_room_dialog).pack(fill="x", pady=2)

        # Utility
        ttk.Button(sidebar, text="🔄 Refresh User List", command=self.request_user_list).pack(fill="x", pady=(10, 5))


        # --- 2. Chat Area ---
        chat_area = ttk.Frame(main_container, padding="0")
        chat_area.grid(row=1, column=1, sticky="nsew", padx=(0, 0))

        # Chat Log
        self.chat_log = scrolledtext.ScrolledText(chat_area, state="disabled", font=("Consolas", 11), wrap="word", height=20, borderwidth=0, relief="flat", 
                                                bg=CHAT_BG, fg=FG_COLOR, insertbackground=FG_COLOR, padx=5, pady=5)
        self.chat_log.pack(fill="both", expand=True, pady=(0, 5))
        
        # --- Apply tags for alignment and styling ---
        self.chat_log.tag_config("bold", font=("Consolas", 11, "bold"))
        
        # Left Alignment (Incoming messages)
        self.chat_log.tag_config("left_align", justify='left') 
        self.chat_log.tag_config("black", foreground=FG_COLOR)
        self.chat_log.tag_config("blue", foreground=ACCENT_COLOR)
        self.chat_log.tag_config("purple", foreground="#c394ff")
        self.chat_log.tag_config("gray", foreground="#a0a0a0")
        self.chat_log.tag_config("green", foreground=SUCCESS_COLOR)
        
        # Right Alignment (Outgoing messages)
        self.chat_log.tag_config("right_align", justify='right')
        self.chat_log.tag_config("right_color", foreground=ACCENT_COLOR)
        # --------------------------------------------------------

        # --- 3. Input Area ---
        input_frame = ttk.Frame(main_container, padding="5 5 5 5")
        input_frame.grid(row=2, column=1, sticky="ew")

        # Media Action Buttons
        media_buttons_frame = ttk.Frame(input_frame)
        media_buttons_frame.pack(side="left", padx=(0, 10))
        
        ttk.Button(media_buttons_frame, text="📎 File", command=self.send_file_dialog, style='TButton').pack(side="left", padx=3)
        ttk.Button(media_buttons_frame, text="🎙 Voice Note", command=self.send_voice_note, style='TButton').pack(side="left", padx=3)

        # Message Entry and Send Button
        self.entry_msg = ttk.Entry(input_frame, font=("Arial", 12))
        self.entry_msg.pack(side="left", fill="x", expand=True, padx=5, ipady=2)
        self.entry_msg.bind("<Return>", self.send_text_message)

        btn_send = ttk.Button(input_frame, text="Send ✉", command=self.send_text_message, style='Send.TButton')
        btn_send.pack(side="left", padx=5)
        
    def _update_target_label(self, *args):
        mode = self.mode_var.get()
        if mode == "PM":
            self.target_label.config(text="Target Username:")
        elif mode == "ROOM":
            self.target_label.config(text="Target Room Name:")
        else: # GLOBAL
            self.target_label.config(text="Target (Not used for Global):")

    # -------------------------------------------------------
    # NETWORK CONNECTION & LISTENING 
    # -------------------------------------------------------
    def connect_to_server(self):
        host = self.entry_ip.get()
        port = int(self.entry_port.get())
        self.username = self.entry_user.get().strip()
        self.server_udp_addr = (host, DEFAULT_UDP_PORT)

        if not self.username:
            messagebox.showerror("Error", "Username cannot be empty")
            return

        try:
            # 1. TCP Setup
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((host, port))
            
            # 2. UDP Setup
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(('', self.local_udp_port))

            # Send Join Message (TCP)
            self.send_json({"type": "join", "from": self.username})
            
            self.is_connected = True
            self._init_chat_screen()
            
            # Start Listener Threads
            threading.Thread(target=self.listen_tcp, daemon=True).start()
            threading.Thread(target=self.listen_udp, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))
            self.cleanup_sockets()

    def cleanup_sockets(self):
        self.is_connected = False
        self.stop_streaming = True
        
        # Reset call state
        self.call_state.set('idle')
        self.audio_stream_active = False
        self.video_stream_active = False
        self.call_mode = None
        self.current_call_target = None
        
        # Close sockets
        if self.tcp_sock:
            try: self.tcp_sock.close()
            except: pass
        if self.udp_sock:
            try: self.udp_sock.close()
            except: pass
            
        cv2.destroyAllWindows()
        
        if hasattr(self, 'btn_call'):
            self.root.after(0, lambda: self.btn_call.config(text="Start Audio Call 🎤", style='Start.TButton'))
        if hasattr(self, 'btn_vid'):
            self.root.after(0, lambda: self.btn_vid.config(text="Start Video Call 📹", style='Start.TButton'))


    def listen_tcp(self):
        buffer = b""
        while self.is_connected:
            try:
                chunk = self.tcp_sock.recv(16384)
                if not chunk:
                    self.log_msg("[System]", "Disconnected from server.", color="gray")
                    self.cleanup_sockets()
                    break

                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        self.handle_incoming_message(msg)
                    except:
                        continue
            except Exception as e:
                if self.is_connected:
                    self.log_msg("[Error]", f"TCP Listener failed: {e}", color=ERROR_COLOR)
                self.cleanup_sockets()
                break

    def listen_udp(self):
        while self.is_connected:
            try:
                data, addr = self.udp_sock.recvfrom(65535) 
                
                delimiter_index = data.find(b'|')
                if delimiter_index == -1: continue 

                json_header_bytes = data[:delimiter_index]
                media_data_bytes = data[delimiter_index+1:]

                try:
                    msg = json.loads(json_header_bytes.decode('utf-8'))
                except json.JSONDecodeError:
                    continue

                mtype = msg.get("type")
                sender = msg.get("from", "?")

                if mtype == "audio_stream":
                    self.play_audio_chunk(media_data_bytes)
                elif mtype == "video_stream":
                    self.show_video_frame(sender, media_data_bytes)
            
            except socket.error as e:
                if not self.is_connected: break
                self.log_msg("[Error]", f"UDP Listener socket error: {e}", color=ERROR_COLOR)
                self.cleanup_sockets() 
                break
            except Exception as e:
                self.log_msg("[Error]", f"UDP Listener general error: {e}", color=ERROR_COLOR)
                self.cleanup_sockets()
                break


    def send_json(self, obj):
        try:
            data = (json.dumps(obj) + "\n").encode("utf-8")
            self.tcp_sock.sendall(data)
        except Exception as e:
            self.log_msg("[Error]", f"TCP Send failed: {e}", color=ERROR_COLOR)

    def send_udp_packet(self, header_obj, media_data_bytes):
        """Sends a structured UDP packet: JSON_Header|Media_Data"""
        try:
            header_bytes = json.dumps(header_obj, separators=(',', ':')).encode('utf-8') 
            packet = header_bytes + b'|' + media_data_bytes
            self.udp_sock.sendto(packet, self.server_udp_addr)
        except Exception as e:
            if not self.stop_streaming: 
                self.log_msg("[Error]", f"UDP Send failed: {e}", color=ERROR_COLOR)


    # -------------------------------------------------------
    # MESSAGE HANDLING LOGIC
    # -------------------------------------------------------
    def handle_incoming_message(self, msg):
        mtype = msg.get("type")
        sender = msg.get("from", "?")

        if mtype == "broadcast":
            self.log_msg(f"[GLOBAL] {sender}", msg.get("msg"))
        elif mtype == "pm":
            self.log_msg(f"[PM] {sender}", msg.get("msg"), color="blue")
        elif mtype == "room_msg":
            self.log_msg(f"[ROOM {msg.get('room')}] {sender}", msg.get("msg"), color="purple")
        elif mtype == "system":
            self.log_msg("[SYSTEM]", msg.get("msg"), color="gray")
        elif mtype == "active_list":
            users = ", ".join(msg.get("users", []))
            self.log_msg("[LIST]", f"Active Users: {users}", color="gray")
        
        # --- File Transfers ---
        elif mtype == "file_init":
            filename = msg.get("filename")
            self.log_msg("[FILE]", f"Receiving '{filename}' from {sender}...", color="gray")
            self.file_buffer[sender] = open(f"recv_{filename}", "wb")
        elif mtype == "file_chunk":
            if sender in self.file_buffer:
                chunk = base64.b64decode(msg.get("chunk"))
                self.file_buffer[sender].write(chunk)
        elif mtype == "file_end":
            if sender in self.file_buffer:
                self.file_buffer[sender].close()
                del self.file_buffer[sender]
                self.log_msg("[FILE]", f"File '{msg.get('filename')}' received successfully!", color="green")
        
        # --- Call Handshake (Auto-Answer Mode) ---
        elif mtype == "call_request":
            if self.call_state.get() == 'idle':
                # AUTO ACCEPT LOGIC
                mode = msg.get("mode")
                self.log_msg("[Call]", f"Incoming {mode} call from {sender}... Auto-accepting.", color="green")
                
                # 1. Send Accepted Response
                self.send_call_response(sender, "accepted", mode)
                
                # 2. Update Local State
                self.call_state.set('accepted')
                self.current_call_target = sender
                self.call_mode = mode
                self.remote_udp_port = msg.get("udp_port")
                
                # 3. Start Streaming IMMEDIATELY
                if mode == 'video':
                    self._start_video_and_audio_streams(sender, False)
                elif mode == 'audio':
                    self._start_audio_stream(sender, False)
                
                self.root.after(0, lambda: self.btn_end_call.config(state='normal'))

            else:
                # Busy, reject automatically
                self.send_call_response(sender, "rejected", msg.get("mode"))
        
        elif mtype == "call_accepted":
            if self.call_state.get() == 'requesting':
                self.remote_udp_port = msg.get("udp_port") 
                self.call_state.set('accepted')
                self.call_response_event.set() # Release the sender thread

        elif mtype == "call_rejected":
            if self.call_state.get() == 'requesting':
                self.call_state.set('rejected')
                self.call_response_event.set() 
                
        elif mtype == "call_end":
            if self.call_state.get() == 'accepted' and self.current_call_target == sender:
                self.log_msg("[Call]", f"Call from {sender} ended remotely.", color="gray")
                self._stop_streams_and_reset_state()


    def log_msg(self, header, text, color="black", align='left'):
        def _update():
            if not hasattr(self, 'chat_log') or not self.is_connected:
                return

            self.chat_log.config(state="normal")
            
            if align == 'right':
                align_tag = "right_align"
                color_tag = "right_color"
            else:
                align_tag = "left_align" 
                color_tag = color
            
            self.chat_log.insert(tk.END, "\n", align_tag) 
            self.chat_log.insert(tk.END, f"{header}: ", ("bold", color_tag, align_tag))
            self.chat_log.insert(tk.END, f"{text}", (color_tag, align_tag))
            
            self.chat_log.see(tk.END)
            self.chat_log.config(state="disabled")
        
        self.root.after(0, _update)

    # -------------------------------------------------------
    # SENDING ACTIONS 
    # -------------------------------------------------------
    def get_target(self):
        mode = self.mode_var.get()
        target = self.entry_target.get().strip()
        
        if mode != "GLOBAL" and not target:
            messagebox.showwarning("Warning", "Please enter a Target Name/Room")
            return None, False
        
        return target, (mode == "ROOM")

    def send_text_message(self, event=None):
        text = self.entry_msg.get().strip()
        if not text: return

        mode = self.mode_var.get()
        target, is_room = self.get_target()
        
        msg_obj = {"from": self.username, "msg": text}

        if mode == "GLOBAL":
            msg_obj["type"] = "broadcast"
            self.log_msg(f"[GLOBAL] {self.username}", text, align='right') 
        elif mode == "PM":
            if not target: return
            msg_obj["type"] = "pm"
            msg_obj["to"] = target
            self.log_msg(f"[To {target}]", text, "blue", align='right') 
        elif mode == "ROOM":
            if not target: return
            msg_obj["type"] = "room_msg"
            msg_obj["room"] = target
            self.log_msg(f"[ROOM {target}] {self.username}", text, "purple", align='right')

        self.send_json(msg_obj)
        self.entry_msg.delete(0, tk.END)

    def send_file_dialog(self):
        filepath = filedialog.askopenfilename()
        if not filepath: return
        
        if filepath.lower().endswith(('.ppt', '.pptx')):
            messagebox.showerror("Error", "This format is not allowed")
            return
        
        mode = self.mode_var.get()
        target, is_room = self.get_target()
        
        if mode == "GLOBAL":
            messagebox.showinfo("Error", "Cannot send files to Global Broadcast. Select PM or Room.")
            return

        threading.Thread(target=self._file_sender_thread, args=(filepath, target, is_room)).start()

    def _file_sender_thread(self, filepath, target, is_room):
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        init_msg = {"type": "file_init", "from": self.username, "filename": filename, "size": filesize}
        if is_room: init_msg["room"] = target
        else: init_msg["to"] = target
        self.send_json(init_msg)
        self.log_msg("[System]", f"File '{filename}' sending...", align='right')

        try:
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(2048)
                    if not chunk: break
                    encoded = base64.b64encode(chunk).decode()
                    chunk_msg = {"type": "file_chunk", "from": self.username, "chunk": encoded}
                    if is_room: chunk_msg["room"] = target
                    else: chunk_msg["to"] = target
                    self.send_json(chunk_msg)
        except Exception as e:
            self.log_msg("[Error]", f"File read failed: {e}", color=ERROR_COLOR)
            return
            
        end_msg = {"type": "file_end", "from": self.username, "filename": filename}
        if is_room: end_msg["room"] = target
        else: end_msg["to"] = target
        self.send_json(end_msg)
        self.log_msg("[System]", f"File '{filename}' sent.", color="green", align='right')

    def send_voice_note(self):
        mode = self.mode_var.get()
        if mode == "GLOBAL":
            messagebox.showinfo("Info", "Select PM or Room for Voice Notes.")
            return

        target, is_room = self.get_target()
        if not target and mode != "GLOBAL": return

        sec = simpledialog.askinteger("Voice Note", "Duration in seconds:", minvalue=1, maxvalue=30)
        if not sec: return

        threading.Thread(target=self._record_and_send_voice, args=(sec, target, is_room)).start()

    def _record_and_send_voice(self, duration, target, is_room):
        self.log_msg("[System]", f"Recording {duration}s...", align='right')
        fs = 44100
        try:
            recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float64')
            sd.wait()
        except Exception as e:
            self.log_msg("[Error]", f"Recording failed: {e}. Check device.", color=ERROR_COLOR)
            return
            
        filename = f"voice_{int(time.time())}.wav"
        wav.write(filename, fs, recording)
        self.log_msg("[System]", "Recording finished. Sending...", align='right')
        
        self._file_sender_thread(filename, target, is_room)
        try: os.remove(filename)
        except: pass

    # -------------------------------------------------------
    # ROOM MANAGEMENT
    # -------------------------------------------------------
    def create_room_dialog(self):
        room = simpledialog.askstring("Create Room", "Room Name:", parent=self.root)
        if room: self.send_json({"type": "create_room", "from": self.username, "room": room})

    def join_room_dialog(self):
        room = simpledialog.askstring("Join Room", "Room Name:", parent=self.root)
        if room: self.send_json({"type": "join_room", "from": self.username, "room": room})

    def leave_room_dialog(self):
        room = simpledialog.askstring("Leave Room", "Room Name:", parent=self.root)
        if room: self.send_json({"type": "leave_room", "from": self.username, "room": room})

    def request_user_list(self):
        self.send_json({"type": "list", "from": self.username})

    # -------------------------------------------------------
    # CALL HANDSHAKE & LIVE STREAMING
    # -------------------------------------------------------

    def initiate_call(self, mode):
        """Starts the call handshake process."""
        if not self.is_connected or self.call_state.get() != 'idle':
            messagebox.showinfo("Call Status", "Already in a call or call attempt in progress.")
            return

        target, is_room = self.get_target()
        if not target: return
        if self.mode_var.get() == "GLOBAL":
            messagebox.showerror("Error", "Cannot call Global. Select PM or Room.")
            return

        self.call_mode = mode
        self.current_call_target = target
        self.call_response_event.clear()
        
        self.root.after(0, lambda: self.btn_call.config(state='disabled'))
        self.root.after(0, lambda: self.btn_vid.config(state='disabled'))
        self.root.after(0, lambda: self.btn_end_call.config(state='normal'))
        
        threading.Thread(target=self._call_sender_thread, args=(target, is_room, mode)).start()

    def _call_sender_thread(self, target, is_room, mode):
        self.call_state.set('requesting')
        
        # 1. Send TCP Call Request
        call_msg = {
            "type": "call_request",
            "from": self.username,
            "mode": mode,
            "udp_port": self.local_udp_port
        }
        if is_room: call_msg["room"] = target
        else: call_msg["to"] = target

        self.send_json(call_msg)
        self.log_msg("[Call]", f"Calling {target} ({mode} mode)... Connecting.", color="blue", align='right')
        
        # 2. Wait for response (Automatic)
        if self.call_response_event.wait(30):
            response = self.call_state.get()
            
            if response == 'accepted':
                self.log_msg("[Call]", f"Call to {target} connected! Stream live.", color="green", align='right')
                # Start Streaming (Video call sends Audio too!)
                if mode == 'video':
                    self._start_video_and_audio_streams(target, is_room)
                elif mode == 'audio':
                    self._start_audio_stream(target, is_room)
                
            elif response == 'rejected':
                self.log_msg("[Call]", f"Call to {target} rejected/busy.", color=ERROR_COLOR, align='right')
                self._reset_call_buttons() 
        else:
            self.log_msg("[Call]", f"Call to {target} timed out.", color=ERROR_COLOR, align='right')
        
        if self.call_state.get() != 'accepted':
            self._stop_streams_and_reset_state()
            self._reset_call_buttons()

    def end_call(self):
        if self.call_state.get() not in ('accepted', 'requesting'): 
            return

        target = self.current_call_target
        if target:
            end_msg = {"type": "call_end", "from": self.username, "to": target}
            self.send_json(end_msg)
        
        if self.call_mode == 'video':
             cv2.destroyAllWindows()
        
        self.log_msg("[Call]", f"Call ended.", color="gray", align='right')
        self._stop_streams_and_reset_state()
        self._reset_call_buttons()


    def _stop_streams_and_reset_state(self):
        self.stop_streaming = True
        self.audio_stream_active = False
        self.video_stream_active = False
        self.call_state.set('idle')
        self.current_call_target = None
        self.call_mode = None
        self.remote_udp_port = None

    def _reset_call_buttons(self):
        self.root.after(0, lambda: self.btn_call.config(text="Start Audio Call 🎤", style='Start.TButton', state='normal'))
        self.root.after(0, lambda: self.btn_vid.config(text="Start Video Call 📹", style='Start.TButton', state='normal'))
        self.root.after(0, lambda: self.btn_end_call.config(state='disabled'))

    def send_call_response(self, receiver, status, mode):
        response_msg = {
            "type": f"call_{status}",
            "from": self.username,
            "to": receiver,
            "mode": mode,
            "udp_port": self.local_udp_port
        }
        self.send_json(response_msg)

    # --- Streaming Helpers ---

    def _start_audio_stream(self, target, is_room):
        self.stop_streaming = False
        self.audio_stream_active = True
        self.root.after(0, lambda: self.btn_call.config(text="STOP Audio Call 🔴", style='Stop.TButton'))
        self.audio_stream_thread = threading.Thread(target=self._audio_stream_thread, args=(target, is_room), daemon=True)
        self.audio_stream_thread.start()

    def _start_video_and_audio_streams(self, target, is_room):
        """Starts BOTH video and audio streaming threads for Video Call Mode."""
        self.stop_streaming = False
        self.video_stream_active = True
        self.audio_stream_active = True # ENABLE AUDIO FOR VIDEO CALL
        
        self.root.after(0, lambda: self.btn_vid.config(text="STOP Video Call 🔴", style='Stop.TButton'))
        
        # 1. Start Audio Thread
        self.audio_stream_thread = threading.Thread(target=self._audio_stream_thread, args=(target, is_room), daemon=True)
        self.audio_stream_thread.start()
        
        # 2. Start Video Thread
        self.video_stream_thread = threading.Thread(target=self._video_stream_thread, args=(target, is_room), daemon=True)
        self.video_stream_thread.start()
        
    def _audio_stream_thread(self, target, is_room):
        self.log_msg("[System]", "Audio Stream Started (UDP)")
        block_size = int(AUDIO_FS * 0.1)
        
        base_header = {"type": "audio_stream", "from": self.username}
        if is_room: base_header["room"] = target
        else: base_header["to"] = target

        stream = None
        try:
            stream = sd.InputStream(samplerate=AUDIO_FS, channels=1, dtype='float32')
            stream.start()

            while not self.stop_streaming and self.audio_stream_active:
                data, overflowed = stream.read(block_size) 
                if not data.any(): continue 
                
                audio_bytes = data.tobytes()
                self.send_udp_packet(base_header, audio_bytes)
                time.sleep(0.01) 
                
        except sd.PortAudioError as e:
            self.log_msg("[ERROR]", f"Audio hardware failure: {e}", color=ERROR_COLOR)
        except Exception as e:
            self.log_msg("[Error]", f"Audio stream failed: {e}", color=ERROR_COLOR)
        finally:
            if stream:
                stream.stop()
                stream.close()
            if self.audio_stream_active:
                self.audio_stream_active = False
                self.root.after(0, lambda: self.btn_call.config(text="Start Audio Call 🎤", style='Start.TButton', state='normal'))
            if self.call_mode == 'audio':
                self._stop_streams_and_reset_state()
            self.log_msg("[System]", "Audio Stream Ended.")

    def play_audio_chunk(self, audio_bytes):
        try:
            audio_data = np.frombuffer(audio_bytes, dtype=np.float32) 
            sd.play(audio_data, samplerate=AUDIO_FS)
        except Exception: 
            pass

    def _video_stream_thread(self, target, is_room):
        self.log_msg("[System]", "Video Stream Started (UDP)")
        cap = cv2.VideoCapture(0)
        cap.set(3, 320)
        cap.set(4, 240)

        base_header = {"type": "video_stream", "from": self.username}
        if is_room: base_header["room"] = target
        else: base_header["to"] = target

        try:
            while not self.stop_streaming and self.video_stream_active and cap.isOpened():
                ret, frame = cap.read()
                if not ret: break
                
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                video_bytes = buffer.tobytes()
                
                self.send_udp_packet(base_header, video_bytes)
                time.sleep(0.05)
        except Exception as e:
            self.log_msg("[Error]", f"Video stream failed: {e}", color=ERROR_COLOR)
        finally:
            if cap and cap.isOpened():
                cap.release()
            cv2.destroyAllWindows()
            if self.video_stream_active:
                self.video_stream_active = False
                self.root.after(0, lambda: self.btn_vid.config(text="Start Video Call 📹", style='Start.TButton', state='normal'))
            if self.call_mode == 'video':
                self._stop_streams_and_reset_state()
            self.log_msg("[System]", "Video Stream Ended.")

    def show_video_frame(self, sender, img_bytes):
        try:
            np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is not None:
                cv2.imshow(f"Video from {sender}", frame)
                cv2.waitKey(1)
        except: 
            pass

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: [cv2.destroyAllWindows(), app.cleanup_sockets(), root.destroy()])
    root.mainloop()