"""
Real-Time Multi-User Chat Application Server (Updated for Group Calls & Message Reliability)

- FIX: Chat and File messages now reliably broadcast to all connected clients (except the sender) 
       when sent to a room, addressing the issue where some users didn't receive messages.
- Handles group_call_request and forwards call_data to all room members.
"""

import socket
import threading
import json
from datetime import datetime

class ChatServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # state
        self.clients = {}         # username -> socket
        self.clients_lock = threading.Lock()

        # NOTE: Rooms state is kept, but chat/file routing now uses the global client list for reliability (see process_message)
        self.rooms = {'General': []}  # room_name -> list of usernames
        self.rooms_lock = threading.Lock()

        # active_calls still tracks both private (user->peer) and group (room->set of users)
        self.active_calls = {}

    def start(self):
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        print(f"[SERVER] Listening on {self.host}:{self.port}")
        try:
            while True:
                client_sock, addr = self.server_sock.accept()
                thr = threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True)
                thr.start()
        except KeyboardInterrupt:
            print("[SERVER] Shutting down")
        finally:
            self.server_sock.close()

    # ---------- sending helpers (unchanged) ----------
    def send_json_to_sock(self, sock, data):
        try:
            payload = json.dumps(data) + "\n"
            sock.send(payload.encode('utf-8'))
        except Exception as e:
            print("[SERVER] send_json_to_sock error:", e)

    def send_to_client(self, username, data):
        with self.clients_lock:
            sock = self.clients.get(username)
            if sock:
                self.send_json_to_sock(sock, data)

    def broadcast(self, data, exclude=None):
        with self.clients_lock:
            for uname, sock in list(self.clients.items()):
                if uname == exclude:
                    continue
                self.send_json_to_sock(sock, data)

    def broadcast_to_room(self, room, data, exclude=None):
        # NOTE: This method is now only used for Group Call Signaling and End Call notifications,
        # where explicit room membership (active_calls[room] or self.rooms[room]) is needed.
        with self.rooms_lock:
            users = list(self.rooms.get(room, []))
        for uname in users:
            if uname == exclude:
                continue
            self.send_to_client(uname, data)

    def broadcast_client_list(self):
        with self.clients_lock:
            clients = list(self.clients.keys())
        self.broadcast({'type':'client_list','clients':clients})

    # ---------- main connection handler (unchanged logic) ----------
    def handle_client(self, client_sock, addr):
        username = None
        try:
            # initial username (raw, not JSON)
            data = client_sock.recv(4096)
            if not data: client_sock.close(); return
            username = data.decode('utf-8').strip()
            if not username: client_sock.close(); return

            with self.clients_lock:
                if username in self.clients:
                    self.send_json_to_sock(client_sock, {'type':'error','message':'Username taken'})
                    client_sock.close(); return
                self.clients[username] = client_sock

            with self.rooms_lock:
                if 'General' not in self.rooms: self.rooms['General'] = []
                if username not in self.rooms['General']: self.rooms['General'].append(username)

            print(f"[SERVER] {username} connected from {addr}")
            self.send_json_to_sock(client_sock, {'type':'welcome','message':f'Welcome {username}','rooms': list(self.rooms.keys())})
            self.broadcast({'type':'user_joined','username':username,'timestamp':datetime.now().strftime('%H:%M:%S')}, exclude=username)
            self.broadcast_client_list()

            buffer = ""
            decoder = json.JSONDecoder()
            while True:
                chunk = client_sock.recv(1024*1024)
                if not chunk: break
                buffer += chunk.decode('utf-8', errors='ignore')
                while buffer:
                    buffer = buffer.lstrip()
                    try:
                        obj, idx = decoder.raw_decode(buffer)
                        buffer = buffer[idx:]
                        self.process_message(username, obj)
                    except ValueError: break
        except Exception as e:
            print("[SERVER] handle_client error for", username, e)
        finally:
            self.disconnect(username)

    # ---------- message routing (FIXED for Chat/File Reliability) ----------
    def process_message(self, sender, message):
        mtype = message.get('type')
        if mtype == 'chat':
            room = message.get('room','General')
            payload = {'type':'chat','sender': sender,'message': message.get('message'),'room': room,'timestamp': datetime.now().strftime('%H:%M:%S')}
            
            # FIX: Use global broadcast for general chat messages. Client filters by current_room.
            self.broadcast(payload, exclude=sender) 
            
        elif mtype == 'private':
            recipient = message.get('recipient')
            payload = {'type':'private','sender': sender,'message': message.get('message'),'timestamp': datetime.now().strftime('%H:%M:%S')}
            self.send_to_client(recipient, payload)
            
        elif mtype == 'file':
            recipient = message.get('recipient')
            payload = {'type':'file','sender': sender,'filename': message.get('filename'),'filedata': message.get('filedata'),'filetype': message.get('filetype'),'timestamp': datetime.now().strftime('%H:%M:%S')}
            if recipient: 
                self.send_to_client(recipient, payload)
            else: 
                # FIX: Use global broadcast for room file messages too.
                self.broadcast(payload, exclude=sender)
                
        elif mtype == 'create_room':
            room_name = message.get('room_name')
            with self.rooms_lock:
                if room_name not in self.rooms: 
                    # Add all current clients to the room's user list for call purposes
                    self.rooms[room_name] = list(self.clients.keys()) 
            self.broadcast({'type':'room_created','room_name':room_name,'creator':sender})
        
        # --- PRIVATE CALL SIGNALING ---
        elif mtype == 'call_request':
            recipient = message.get('recipient')
            self.send_to_client(recipient, {'type':'call_request','caller':sender,'call_type':message.get('call_type'),'timestamp': datetime.now().strftime('%H:%M:%S')})
        elif mtype == 'call_response':
            caller = message.get('caller')
            accepted = message.get('accepted')
            call_type = message.get('call_type','both')
            if accepted:
                self.active_calls[sender] = caller
                self.active_calls[caller] = sender
            self.send_to_client(caller, {'type':'call_response','responder':sender,'accepted':accepted,'call_type':call_type})

        # --- GROUP CALL SIGNALING ---
        elif mtype == 'group_call_request':
            room = message.get('room')
            call_type = message.get('call_type','video')
            with self.rooms_lock:
                if room not in self.rooms: return
            
            if room not in self.active_calls: self.active_calls[room] = set()
            self.active_calls[room].add(sender)
            
            # Broadcast request to all room members (excluding the caller)
            self.broadcast_to_room(room, {
                'type':'group_call_request',
                'room':room,
                'caller':sender,
                'call_type':call_type,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }, exclude=sender)

        # --- MEDIA DATA FORWARDING ---
        elif mtype == 'call_data':
            if 'peer' in message: # Private Call Data
                peer = message.get('peer')
                payload = {'type':'call_data','sender':sender,'data': message.get('data'),'data_type': message.get('data_type')}
                self.send_to_client(peer, payload)
            
            elif 'room' in message: # Group Call Data
                room = message.get('room')
                if room in self.active_calls and isinstance(self.active_calls[room], set):
                    # Forward to all active call members in the room (excluding sender)
                    for user in list(self.active_calls[room]):
                        if user != sender:
                            payload = {'type':'call_data','sender':sender,'data': message.get('data'),'data_type': message.get('data_type')}
                            self.send_to_client(user, payload)
            else:
                print("[SERVER] Invalid call_data payload (missing peer/room)")


        # --- END CALL ---
        elif mtype == 'end_call':
            is_group = message.get('is_group', False)
            
            if is_group:
                room = message.get('room')
                if room in self.active_calls and isinstance(self.active_calls[room], set):
                    self.active_calls[room].discard(sender)
                    if not self.active_calls[room]:
                        self.active_calls.pop(room, None)
                        self.broadcast_to_room(room, {'type':'call_ended','peer':room}) # Notify room call is over
                self.send_to_client(sender, {'type':'call_ended','peer':room}) # Self-confirmation
                
            else: # Private Call
                if sender in self.active_calls:
                    peer = self.active_calls.pop(sender, None)
                    if peer and peer in self.active_calls:
                        self.active_calls.pop(peer, None)
                        self.send_to_client(peer, {'type':'call_ended','peer':sender})
                self.send_to_client(sender, {'type':'call_ended','peer':sender})

        else:
            print("[SERVER] Unknown message type from", sender, mtype)

    def disconnect(self, username):
        if not username: return
        with self.clients_lock:
            sock = self.clients.pop(username, None)
            if sock:
                try: sock.close()
                except: pass
        with self.rooms_lock:
            for room, users in self.rooms.items():
                if username in users: users.remove(username)
        
        # End any active private call
        if username in self.active_calls:
            peer = self.active_calls.pop(username, None)
            if peer and peer in self.active_calls:
                self.active_calls.pop(peer, None)
                self.send_to_client(peer, {'type':'call_ended','peer':username})

        # End any active group calls the user was in
        rooms_to_check = list(self.active_calls.keys())
        for room in rooms_to_check:
            if isinstance(self.active_calls.get(room), set) and username in self.active_calls[room]:
                 self.active_calls[room].discard(username)
                 if not self.active_calls[room]:
                    self.active_calls.pop(room, None)
                    self.broadcast_to_room(room, {'type':'call_ended','peer':room})

        print(f"[SERVER] {username} disconnected")
        self.broadcast({'type':'user_left','username':username,'timestamp':datetime.now().strftime('%H:%M:%S')})
        self.broadcast_client_list()

if __name__ == '__main__':
    server = ChatServer(host='0.0.0.0', port=5555)   
    server.start()