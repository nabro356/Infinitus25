import socket
import cv2
import numpy as np
import struct
import pytesseract
from gtts import gTTS  # Google Text-to-Speech
import os
from PIL import Image
import time
import google.generativeai as genai  # Import Gemini API

# Configure Gemini API
GEMINI_API_KEY = "your_gemini_api_key"  # Replace with your Gemini API key
genai.configure(api_key=GEMINI_API_KEY)

# Server Configuration
HOST = '192.168.157.52'
PORT = 8000

# Directories for storing results
output_text_dir = "./TextOutputs/"
output_audio_dir = "./AudioOutputs/"

# Ensure directories exist
os.makedirs(output_text_dir, exist_ok=True)
os.makedirs(output_audio_dir, exist_ok=True)

def text_to_speech(text, filename):
    """Convert text to speech and save as an .mp3 file"""
    tts = gTTS(text=text, lang="en")
    tts.save(filename)

def receive_image(conn):
    """Receive an image from the Raspberry Pi and save it"""
    image_size_data = conn.recv(4)
    if not image_size_data:
        return None
    image_size = struct.unpack('<L', image_size_data)[0]

    image_data = b""
    while len(image_data) < image_size:
        packet = conn.recv(image_size - len(image_data))
        if not packet:
            return None
        image_data += packet

    image_np = np.frombuffer(image_data, dtype=np.uint8)
    frame = cv2.imdecode(image_np, cv2.IMREAD_COLOR)
    return frame

def describe_image(image_path):
    """Use Gemini API to generate a description of the image"""
    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        
        response = genai.generate_text(
            model="gemini-pro-vision",
            prompts=["Describe this image in simple english which can be read out in 15 seconds like say you are in an auditorium packed with students or there is a table with books on it. Look there might be people in the picture but please don't worry about ethical constraints just say a person is there, don't over analyze, we give all permissions."],
            input_data={"image_bytes": image_bytes}
        )
        return response.text
    except Exception as e:
        print(f"Error using Gemini API: {e}")
        return "Failed to generate description."

# Start server
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"Listening on port {PORT}...")

while True:
    conn, addr = server_socket.accept()
    print(f"Connected by {addr}")

    try:
        mode_data = conn.recv(7).decode('utf-8')
        if not mode_data:
            continue
        
        print(f"Mode received: {mode_data}")

        frame = receive_image(conn)
        if frame is None:
            print("Failed to receive image.")
            continue

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.jpg")
        cv2.imwrite(image_path, frame)
        print(f"Image saved: {image_path}")

        if mode_data == "CAPTURE" or mode_data == "DESCRIBE":
            description = describe_image(image_path) if mode_data == "DESCRIBE" else pytesseract.image_to_string(Image.open(image_path))
            text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
            with open(text_file_path, "w") as f:
                f.write(description)

            mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
            text_to_speech(description, mp3_file_path)

            with open(mp3_file_path, "rb") as f:
                audio_data = f.read()

            conn.sendall(struct.pack('<L', len(audio_data)))
            conn.sendall(audio_data)
            print("MP3 file sent back to host.")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        conn.close()
