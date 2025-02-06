import socket
import cv2
import numpy as np
import struct
import pytesseract
from gtts import gTTS
import os
import time
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.service_account import Credentials

# Google Drive API Configuration
CREDENTIALS_FILE = "southern-shade-450017-n1-51653cac7517.json"
DRIVE_FOLDER_ID = "1IqwZ7rO690pPITRP5YTH1QWPh7Ip9VY2"

# Authenticate Google Drive API
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/drive"])
drive_service = build("drive", "v3", credentials=creds)

# Server Configuration
HOST = "192.168.157.52"
PORT = 8000  

# Local Directories
output_audio_dir = "./AudioOutputs/"
local_image_dir = "./ReceivedImages/"
os.makedirs(output_audio_dir, exist_ok=True)
os.makedirs(local_image_dir, exist_ok=True)

def receive_image(conn):
    """Receive an image from Raspberry Pi."""
    try:
        image_size_data = conn.recv(4)
        if not image_size_data:
            return None
        image_size = struct.unpack("<L", image_size_data)[0]

        # Receive image data
        image_data = b""
        while len(image_data) < image_size:
            packet = conn.recv(image_size - len(image_data))
            if not packet:
                return None
            image_data += packet

        # Convert received bytes to an image
        return cv2.imdecode(np.frombuffer(image_data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"[ERROR] Receiving image failed: {e}")
        return None

def upload_to_drive(file_path, mime_type):
    """Upload a file to Google Drive."""
    file_name = os.path.basename(file_path)
    file_metadata = {"name": file_name, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype=mime_type)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file["id"]

def get_latest_mp3_from_drive():
    """Wait and get the latest MP3 file from Google Drive."""
    while True:
        results = drive_service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='audio/mpeg'",
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc"
        ).execute()
        
        files = results.get("files", [])
        if files:
            return files[0]  # Return latest MP3 file
        
        print("[INFO] Waiting for MP3 in Drive...")
        time.sleep(10)  # Check every 10 seconds

def download_file_from_drive(file_id, output_path):
    """Download a file from Google Drive."""
    request = drive_service.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

def delete_file_from_drive(file_id):
    """Delete a file from Google Drive."""
    drive_service.files().delete(fileId=file_id).execute()

def send_mp3(conn, file_path):
    """Send MP3 file in chunks to Raspberry Pi."""
    try:
        with open(file_path, "rb") as f:
            audio_data = f.read()
        
        conn.sendall(struct.pack("<L", len(audio_data)))  # Send file size

        # Send in chunks
        chunk_size = 1024
        for i in range(0, len(audio_data), chunk_size):
            conn.sendall(audio_data[i:i+chunk_size])

        print("[INFO] MP3 sent successfully.")
    except Exception as e:
        print(f"[ERROR] Sending MP3 failed: {e}")

# Start server
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"Listening on port {PORT}...")

while True:
    conn, addr = server_socket.accept()
    print(f"Connected by {addr}")

    try:
        while True:
            # Receive mode ("CAPTURE" or "DESCRIBE")
            mode_data = conn.recv(7).decode("utf-8").strip()
            if not mode_data:
                break
            
            print(f"[INFO] Mode received: {mode_data}")

            # Receive and process image
            frame = receive_image(conn)
            if frame is None:
                print("[ERROR] Image reception failed.")
                break

            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = os.path.join(local_image_dir, f"{mode_data}_{timestamp}.jpg")
            cv2.imwrite(image_path, frame)
            print(f"[INFO] Image saved: {image_path}")

            if mode_data == "DESCRIBE":
                # Upload image to Google Drive
                uploaded_image_id = upload_to_drive(image_path, "image/jpeg")
                print(f"[INFO] Uploaded to Drive with ID: {uploaded_image_id}")

                # Wait for MP3 file in Drive
                latest_mp3 = get_latest_mp3_from_drive()
                mp3_file_id = latest_mp3["id"]
                mp3_local_path = os.path.join(output_audio_dir, latest_mp3["name"])

                # Download the MP3 file
                download_file_from_drive(mp3_file_id, mp3_local_path)
                print(f"[INFO] Downloaded MP3 file: {mp3_local_path}")

                # Send the MP3 file back to Raspberry Pi
                send_mp3(conn, mp3_local_path)

                # Delete files from Drive only after successful transmission
                delete_file_from_drive(uploaded_image_id)
                delete_file_from_drive(mp3_file_id)
                print("[INFO] Deleted image and MP3 from Drive.")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        conn.close()
