import socket
import cv2
import numpy as np
import struct
import os
import time
import requests
from gtts import gTTS  # Google Text-to-Speech
from PIL import Image
from google.cloud import vision

# Google API Setup
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'vision-api-450017-cbe451515384.json'  # Update this path
vision_client = vision.ImageAnnotatorClient()
GEMINI_API_KEY = "AIzaSyBjuQHU8GYEPm9Fj0Rrna26-E6zdwXAhLg"  # Update this

# Server Configuration
HOST = '192.168.157.52'  # Listen on all available network interfaces
PORT = 8000

# Directories for storing results
output_audio_dir = "./AudioOutputs/"
os.makedirs(output_audio_dir, exist_ok=True)

def text_to_speech(text, filename):
    """Convert text to speech and save as an .mp3 file"""
    tts = gTTS(text=text, lang="en")
    tts.save(filename)

def apply_google_vision(image_path):
    """Use Google Vision API to extract labels from an image."""
    with open(image_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = vision_client.label_detection(image=image)
    labels = [label.description for label in response.label_annotations]
    return labels

def generate_scene_description(labels):
    """Use Gemini API to generate a structured scene description."""
    prompt_text = f"Generate a simple English scene description under 20 seconds using these labels: {', '.join(labels)}"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    data = {"contents": [{"parts": [{"text": prompt_text}]}]}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return "Scene description unavailable."

def receive_image(conn):
    """Receive an image from the Raspberry Pi and save it."""
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
    return cv2.imdecode(image_np, cv2.IMREAD_COLOR)

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
            mode_data = conn.recv(7).decode('utf-8').strip()
            if not mode_data:
                break
            print(f"Mode received: {mode_data}")

            frame = receive_image(conn)
            if frame is None:
                print("Failed to receive image.")
                break

            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = f"./TempImages/{mode_data}_{timestamp}.jpg"
            cv2.imwrite(image_path, frame)
            print(f"Image saved: {image_path}")

            if mode_data == "DESCRIBE":
                labels = apply_google_vision(image_path)
                scene_description = generate_scene_description(labels)
                print(f"Scene Description: {scene_description}")

                mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
                text_to_speech(scene_description, mp3_file_path)
                print(f"TTS saved as MP3: {mp3_file_path}")

                with open(mp3_file_path, "rb") as f:
                    audio_data = f.read()
                conn.sendall(struct.pack('<L', len(audio_data)))
                conn.sendall(audio_data)
                print("MP3 file sent back to host.")

                #os.remove(image_path)  # Delete image after processing
                #os.remove(mp3_file_path)  # Delete MP3 after sending
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
