import socket
import threading
import json
import traceback
from typing import Dict, Set, Tuple

HOST = "0.0.0.0"   # listen on all interfaces
TCP_PORT = 9009
UDP_PORT = 9010 # Dedicated port for UDP media traffic

# Shared global state
clients_lock = threading.Lock()
clients: Dict[str, socket.socket] = {}       # username -> TCP socket
conn_to_user: Dict[socket.socket, str] = {}  # TCP socket -> username

# Mapping for UDP addresses
user_to_udp_addr: Dict[str, Tuple[str, int]] = {} # username -> (ip, port) for receiving UDP

rooms_lock = threading.Lock()
rooms: Dict[str, Set[str]] = {}               # room_name -> set(usernames)

# UDP Socket
udp_sock: socket.socket | None = None

# Helper: send JSON object as a newline-terminated line (TCP)
def send_json(sock: socket.socket, obj: dict):
    """Sends a JSON object over a TCP socket."""
    try:
        # Use separators=(',', ':') for compact JSON and append newline
        data = (json.dumps(obj, separators=(',', ':')) + '\n').encode('utf-8')
        sock.sendall(data)
    except Exception:
        # socket may be closed / broken - ignore here
        pass

# --- FIXED: ADDED MISSING BROADCAST FUNCTION ---
def broadcast(obj: dict, exclude_username: str = None):
    """Sends a JSON object to all connected clients over TCP."""
    with clients_lock:
        targets = [s for user, s in clients.items() if user != exclude_username]
    for s in targets:
        send_json(s, obj)
# ----------------------------------------------

# Broadcast to a specific room (TCP - for control/text/file)
def broadcast_room(room: str, obj: dict, exclude_username: str = None):
    """Sends a JSON object to all TCP sockets in a specified room."""
    with rooms_lock:
        members = set(rooms.get(room, set()))
    to_send = []
    with clients_lock:
        for user in members:
            if user == exclude_username:
                continue
            sock = clients.get(user)
            if sock:
                to_send.append(sock)
    for s in to_send:
        send_json(s, obj)

# Send active user list to everyone or a single connection
def send_active_users(to_sock: socket.socket = None):
    """Sends the list of active users over TCP."""
    with clients_lock:
        userlist = list(clients.keys())
    msg = {"type": "active_list", "users": userlist}
    
    if to_sock:
        send_json(to_sock, msg)
    else:
        # Broadcast to all
        with clients_lock:
            targets = list(clients.values())
        for s in targets:
            send_json(s, msg)

def safe_remove_client_by_socket(sock: socket.socket):
    """Safely removes a client and broadcasts disconnect notification."""
    username = None
    with clients_lock:
        username = conn_to_user.pop(sock, None)
        if username and username in clients:
            try:
                del clients[username]
            except KeyError:
                pass
        # Remove UDP address on disconnect
        if username in user_to_udp_addr:
            print(f"[UDP] Unregistered {username}'s UDP address.")
            del user_to_udp_addr[username]

    if username:
        # remove from all rooms
        with rooms_lock:
            for r in list(rooms.keys()):
                if username in rooms[r]:
                    rooms[r].discard(username)
        
        # notify others via TCP
        broadcast({"type": "system", "msg": f"{username} left the chat."})
        send_active_users()


def handle_udp_packet(data: bytes, addr: Tuple[str, int]):
    """
    Handles incoming UDP data (media streams) and relays it to the target(s).
    The format is expected to be: JSON_Header|Base64_Media_Data
    """
    global udp_sock
    try:
        # Find the delimiter '|' which separates JSON header from media data
        delimiter_index = data.find(b'|')
        if delimiter_index == -1:
            return 
        
        json_header_bytes = data[:delimiter_index]
        
        try:
            msg = json.loads(json_header_bytes.decode('utf-8'))
        except json.JSONDecodeError:
            print(f"[UDP] Malformed JSON header from {addr}")
            return

        mtype = msg.get('type')
        username = msg.get('from')
        to = msg.get('to')
        room = msg.get('room')
        
        if mtype not in ('audio_stream', 'video_stream') or not username:
            return

        # 1. Register the client's UDP address upon first stream packet
        with clients_lock:
            if username not in user_to_udp_addr:
                user_to_udp_addr[username] = addr
                print(f"[UDP] Registered {username} UDP address via first packet: {addr}")

        # 2. Forward the entire raw packet (header + media data)
        
        # Forward to a specific user (PM)
        if to:
            with clients_lock:
                target_addr = user_to_udp_addr.get(to)
            if target_addr and udp_sock:
                udp_sock.sendto(data, target_addr)

        # Forward to a room
        elif room:
            with rooms_lock:
                members = set(rooms.get(room, set()))
            
            target_addrs = []
            with clients_lock:
                for member in members:
                    if member != username: # Do not send back to sender
                        addr = user_to_udp_addr.get(member)
                        if addr:
                            target_addrs.append(addr)
            
            if udp_sock:
                for target_addr in target_addrs:
                    udp_sock.sendto(data, target_addr)

    except Exception as e:
        print(f"[!] UDP handling error: {e}")
        traceback.print_exc()

def udp_listener_thread():
    """Listens for and relays media streams over UDP."""
    print(f"UDP listener started on {HOST}:{UDP_PORT}")
    global udp_sock
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp_sock.bind((HOST, UDP_PORT))
        
        while True:
            try:
                data, addr = udp_sock.recvfrom(65535) 
                # Hand off packet processing to a worker thread
                threading.Thread(target=handle_udp_packet, args=(data, addr), daemon=True).start()
            except socket.error:
                break
            except Exception as e:
                print(f"[!] UDP thread inner loop error: {e}")
                traceback.print_exc()
    finally:
        if udp_sock:
            udp_sock.close()
        print("UDP listener stopped.")


def handle_client_connection(conn: socket.socket, addr: Tuple[str, int]):
    """Handles TCP control and data (text, file, stream initiation)."""
    print(f"[+] New TCP connection from {addr}")
    buffer = b''    
    username = None 
    try:
        # --- JOIN / REGISTRATION LOOP ---
        while True:  
            chunk = conn.recv(4096)
            if not chunk:
                return
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                try:
                    obj = json.loads(line.decode('utf-8'))
                except Exception:
                    continue 
                if obj.get('type') == 'join' and 'from' in obj:
                    username = obj['from']  
                    
                    # register (handle collision)
                    with clients_lock: 
                        base = username  
                        counter = 1    
                        while username in clients:
                            username = f"{base}_{counter}"
                            counter += 1
                        clients[username] = conn
                        conn_to_user[conn] = username
                    print(f"[=] Registered user: {username} from {addr}")
                    
                    # Tell client the UDP server port (Crucial for Client setup)
                    send_json(conn, {"type": "system", "msg": f"Welcome {username}! UDP Port: {UDP_PORT}"})
                    
                    # tell everyone else
                    broadcast({"type": "system", "msg": f"{username} joined the chat."}, exclude_username=username)
                    send_active_users()
                    break # Exit registration loop
            if username:
                break
        
        # --- MAIN TCP RECEIVE LOOP (Control & Data) ---
        while True:
            chunk = conn.recv(16384) 
            if not chunk:
                break
            buffer += chunk
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                try:
                    msg = json.loads(line.decode('utf-8'))
                except Exception:
                    continue
                
                mtype = msg.get('type')
                
                # --- TEXT & CONTROL MESSAGES ---
                if mtype == 'broadcast':
                    text = msg.get('msg', '')
                    broadcast({"type": "broadcast", "from": username, "msg": text}, exclude_username=username)
                
                elif mtype == 'pm':
                    to = msg.get('to')
                    text = msg.get('msg', '')
                    with clients_lock:
                        target_sock = clients.get(to)
                    if target_sock:  
                        send_json(target_sock, {"type": "pm", "from": username, "msg": text})
                    else:
                        send_json(conn, {"type": "system", "msg": f"User {to} not found or offline."})

                # --- ROOM OPERATIONS (TCP) ---
                elif mtype == 'create_room':
                    room = msg.get('room')
                    with rooms_lock: rooms.setdefault(room, set())
                    send_json(conn, {"type": "system", "msg": f"Room '{room}' created."})

                elif mtype == 'join_room':
                    room = msg.get('room')  
                    with rooms_lock: rooms.setdefault(room, set()).add(username)
                    send_json(conn, {"type": "system", "msg": f"You joined room '{room}'."})

                elif mtype == 'leave_room':
                    room = msg.get('room')
                    with rooms_lock: 
                        if room in rooms and username in rooms[room]:
                            rooms[room].discard(username)
                    send_json(conn, {"type": "system", "msg": f"You left room '{room}'."})

                elif mtype == 'room_msg':
                    room = msg.get('room')
                    text = msg.get('msg', '')
                    broadcast_room(room, {"type": "room_msg", "from": username, "room": room, "msg": text}, exclude_username=username)

                elif mtype == 'list':
                    send_active_users(to_sock=conn)

                # --- FILE TRANSFER (TCP) ---
                elif mtype in ('file_init', 'file_chunk', 'file_end'):
                    to = msg.get('to')
                    room = msg.get('room')
                    
                    forwarded = dict(msg)
                    forwarded['from'] = username

                    if to:
                        with clients_lock: target_sock = clients.get(to)
                        if target_sock:
                            send_json(target_sock, forwarded)
                        else:
                            send_json(conn, {"type": "system", "msg": f"User {to} not found or offline."})
                    elif room:
                        broadcast_room(room, forwarded, exclude_username=username)
                    else:
                        send_json(conn, {"type": "system", "msg": "File transfer missing 'to' or 'room' field."})

                # --- UDP STREAM INITIATION (TCP Control Message) ---
                elif mtype == 'stream_init':
                    client_udp_port = msg.get('udp_port')
                    if client_udp_port and username:
                        # Use the client's TCP IP address (addr[0]) but the UDP port provided by the client
                        client_ip = addr[0] 
                        client_udp_addr = (client_ip, client_udp_port)
                        with clients_lock:
                             user_to_udp_addr[username] = client_udp_addr
                        print(f"[{username}] registered UDP: {client_udp_addr} via stream_init")
                        send_json(conn, {"type": "system", "msg": "UDP address registered."})
                    else:
                        send_json(conn, {"type": "system", "msg": "Missing 'udp_port' or not registered."})
                
                # --- CALL SIGNALING (TCP - Requirement for Calls) ---
                elif mtype in ('call_request', 'call_accepted', 'call_rejected', 'call_end'):
                    to = msg.get('to')
                    forwarded = dict(msg) # Forward the whole object as is
                    
                    with clients_lock:
                        target_sock = clients.get(to)
                    
                    if target_sock:
                        send_json(target_sock, forwarded)
                    else:
                        # Only send error if it's a request, otherwise ignore
                        if mtype == 'call_request':
                            send_json(conn, {"type": "system", "msg": f"User {to} is offline."})


                # --- OTHER / UNKNOWN ---
                else:
                    send_json(conn, {"type": "system", "msg": f"Unknown message type: {mtype}"})

    except Exception as e:
        print(f"[!] Exception in client thread ({addr}): {e}")
        traceback.print_exc()
    finally:
        try: conn.close()
        except: pass
        safe_remove_client_by_socket(conn)
        print(f"[-] Connection closed {addr}")

def main():
    print("Starting HYBRID TCP/UDP chat server...")
    
    # Start UDP listener thread first
    udp_thread = threading.Thread(target=udp_listener_thread, daemon=True)
    udp_thread.start()

    # Start TCP listener
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        tcp_sock.bind((HOST, TCP_PORT))
        tcp_sock.listen(100) 
        print(f"TCP control listening on {HOST}:{TCP_PORT}")

        while True:
            conn, addr = tcp_sock.accept()
            # Start a new thread for each TCP connection
            t = threading.Thread(target=handle_client_connection, args=(conn, addr), daemon=True)    
            t.start() 
    except KeyboardInterrupt:
        print("Shutting down server...")
    finally:
        tcp_sock.close()    

if __name__ == "__main__":
    main()