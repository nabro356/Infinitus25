import socket
import cv2
import numpy as np
import struct
import pytesseract
from gtts import gTTS  # Google Text-to-Speech
import os
import time
from PIL import Image
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.service_account import Credentials

# Google Drive API Configuration
CREDENTIALS_FILE = "southern-shade-450017-n1-51653cac7517.json"  # Path to your service account JSON file
DRIVE_FOLDER_ID = "1IqwZ7rO690pPITRP5YTH1QWPh7Ip9VY2"  # Google Drive folder ID where images & MP3s are stored

# Authenticate Google Drive API
creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=["https://www.googleapis.com/auth/drive"])
drive_service = build("drive", "v3", credentials=creds)

# Server Configuration
HOST = "192.168.157.52"  # Listen on all available network interfaces
PORT = 8000

# Local Directories for Storing Results
output_text_dir = "./TextOutputs/"
output_audio_dir = "./AudioOutputs/"
local_image_dir = "./ReceivedImages/"

# Ensure directories exist
os.makedirs(output_text_dir, exist_ok=True)
os.makedirs(output_audio_dir, exist_ok=True)
os.makedirs(local_image_dir, exist_ok=True)

def text_to_speech(text, filename):
    """Convert text to speech and save as an .mp3 file"""
    tts = gTTS(text=text, lang="en")
    tts.save(filename)

def apply_ocr(image_path):
    """Perform OCR on an image and return the extracted text"""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text.strip()  # Remove extra spaces and newlines

def receive_image(conn):
    """Receive an image from the Raspberry Pi and save it"""
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
    image_np = np.frombuffer(image_data, dtype=np.uint8)
    frame = cv2.imdecode(image_np, cv2.IMREAD_COLOR)
    return frame

def upload_to_drive(file_path, mime_type):
    """Upload a file to Google Drive"""
    file_name = os.path.basename(file_path)
    file_metadata = {"name": file_name, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype=mime_type)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file["id"]

def get_latest_mp3_from_drive():
    """Wait and get the latest MP3 file from Google Drive"""
    while True:
        results = drive_service.files().list(
            q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='audio/mpeg'",
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc"
        ).execute()
        
        files = results.get("files", [])
        if files:
            return files[0]  # Return the latest MP3 file info
        
        print("Waiting for latest MP3 file in Drive...")
        time.sleep(10)  # Check every 10 seconds

def download_file_from_drive(file_id, output_path):
    """Download a file from Google Drive"""
    request = drive_service.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

def delete_file_from_drive(file_id):
    """Delete a file from Google Drive"""
    drive_service.files().delete(fileId=file_id).execute()

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
            # Receive mode information (CAPTURE or DESCRIBE)
            mode_data = conn.recv(7).decode("utf-8").strip()  # "CAPTURE" or "DESCRIBE"
            if not mode_data:
                break
            
            print(f"Mode received: {mode_data}")

            # Receive and process the image
            frame = receive_image(conn)
            if frame is None:
                print("Failed to receive image.")
                break

            # Save the received image locally
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = os.path.join(local_image_dir, f"{mode_data}_{timestamp}.jpg")
            cv2.imwrite(image_path, frame)
            print(f"Image saved: {image_path}")

            if mode_data == "CAPTURE":
                # Apply OCR and save extracted text
                text = apply_ocr(image_path)
                text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
                with open(text_file_path, "w") as f:
                    f.write(text)
                print(f"Extracted text saved: {text_file_path}")

                # Convert text to speech and save as .mp3 file
                mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
                text_to_speech(text, mp3_file_path)
                print(f"TTS saved as MP3: {mp3_file_path}")

                # Send the .mp3 file back to the Raspberry Pi
                with open(mp3_file_path, "rb") as f:
                    audio_data = f.read()
                
                conn.sendall(struct.pack("<L", len(audio_data)))  # Send audio file size
                conn.sendall(audio_data)  # Send audio file content
                print("MP3 file sent back to host.")

            elif mode_data == "DESCRIBE":
                # Upload received JPEG image to Google Drive
                uploaded_image_id = upload_to_drive(image_path, "image/jpeg")
                print(f"Uploaded image to Drive with ID: {uploaded_image_id}")

                # Wait for the latest MP3 file in Google Drive
                latest_mp3 = get_latest_mp3_from_drive()
                mp3_file_id = latest_mp3["id"]
                mp3_file_name = latest_mp3["name"]
                mp3_local_path = os.path.join(output_audio_dir, mp3_file_name)

                # Download the latest MP3 file
                download_file_from_drive(mp3_file_id, mp3_local_path)
                print(f"Downloaded MP3 file: {mp3_local_path}")

                # Send the MP3 file back to Raspberry Pi
                with open(mp3_local_path, "rb") as f:
                    audio_data = f.read()

                conn.sendall(struct.pack("<L", len(audio_data)))  # Send audio file size
                conn.sendall(audio_data)  # Send audio file content
                print("MP3 file sent back to host.")

                # Delete the uploaded image and MP3 file from Drive
                delete_file_from_drive(uploaded_image_id)
                delete_file_from_drive(mp3_file_id)
                print("Deleted image and MP3 file from Drive.")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        conn.close()
