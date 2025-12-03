📘 README.md — Python Multimedia Chat System (TCP + UDP)
📌 Project Overview

This project is a Python-based Multimedia Chat System that supports:

✅ Multi-client text messaging

✅ Private messaging (PM)

✅ Group / Room messaging

✅ File sharing

✅ Voice notes

✅ Real-time audio calls

✅ Real-time video calls

✅ Active users list

✅ Dark-mode GUI

✅ Hybrid TCP + UDP architecture

It uses TCP for control, messaging, and file transfer, while UDP is used for real-time audio and video streaming to ensure low latency and smooth performance.

The user-friendly Tkinter GUI makes it easy to communicate, create rooms, share files, and start audio/video calls — all inside one application.

⚙️ Technologies Used

Python

Socket Programming (TCP & UDP)

Multithreading

Tkinter (GUI)

OpenCV (Video)

SoundDevice (Audio)

NumPy & Scipy (Media Processing)

JSON (Data Communication)

🧠 How It Works
🔷 TCP is used for:

Text messages

File transfer

Room creation / join / leave

Call signaling (request, accept, reject, end)

User registration

User list updates

🔶 UDP is used for:

Live audio streaming

Live video streaming

This hybrid model makes the system fast, stable, and suitable for real-time communication.

🖥️ Features
🗨️ Messaging

Broadcast messages to all users

Send private messages (PM)

Send group messages in rooms

🎙 Voice Notes

Record and send voice messages with duration control

📎 File Sharing

Secure file transfer to individuals or rooms

Automatic receive & save

👥 Chat Rooms

Create rooms

Join rooms

Leave rooms

Message within rooms

🎧 Audio Calls

One-to-one or room-based audio calls

Real-time streaming using UDP

📹 Video Calls

Live webcam streaming

Audio included in video mode

Uses OpenCV + UDP stream

🔒 Smart Features

Auto-username collision handling

Auto call answering (if enabled)

Automatic UDP registration

Dark modern UI

Error handling & reconnection

🗂️ File Structure
Chat-System/
│
├── Chat_Server.py      # Main server file (TCP + UDP)
├── Chat_Client.py      # GUI Client with audio/video support
└── README.md            # Project Documentation

🛠️ Required Libraries

Install these before running the project:

pip install sounddevice scipy numpy opencv-python


(Tkinter, threading, socket, json are built-in in Python)

🚀 How to Run
🔹 Step 1: Start the Server

Open terminal and run:

python Chat_Server.py


Server will start listening on:

TCP → 9009

UDP → 9010

🔹 Step 2: Start the Client

In a new terminal:

python Chat_Client.py


Then enter:

Server IP: (e.g. 127.0.0.1 or LAN IP)

Port: 9009

Username

Click Connect to Server

🎥 Usage Guide
Feature	How to Use
Text message	Type and press Enter
Private Message	Select PM and enter target username
Room message	Select Room and enter room name
Create room	➕ Create Room
Join room	➡ Join Room
File send	📎 File
Voice note	🎙 Voice
Audio Call	Start Audio Call 🎤
Video Call	Start Video Call 📹
End Call	End Current Call 🛑
🧩 Future Improvements

Encryption (AES + SSL)

Screen sharing

Mobile client

Emoji & stickers

Database chat history

Authentication system

👤 Author

Humair Ali
UET | Computer Science
Python | Networking | OOP | Cyber Security

📜 License

This project is for learning & educational use.
Feel free to modify and expand it 🚀
