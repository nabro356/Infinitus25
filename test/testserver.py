import socket
import cv2
import numpy as np
import struct
import pytesseract
import pyttsx3
import os
from PIL import Image
import io

# Server Configuration
HOST = '192.168.157.52'  # Listen on all available network interfaces
PORT = 8000

# Directories for storing results
output_text_dir = "./TextOutputs/"
output_audio_dir = "./AudioOutputs/"

# Ensure directories exist
os.makedirs(output_text_dir, exist_ok=True)
os.makedirs(output_audio_dir, exist_ok=True)

# Initialize TTS engine
engine = pyttsx3.init()

def text_to_speech(text, filename):
    """Convert text to speech and save as a .wav file"""
    engine.save_to_file(text, filename)
    engine.runAndWait()

def apply_ocr(image_path):
    """Perform OCR on an image and return the extracted text"""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text.strip()  # Remove extra spaces and newlines

def receive_image(conn):
    """Receive an image from the Raspberry Pi and save it"""
    # Receive image size
    image_size_data = conn.recv(4)
    if not image_size_data:
        return None
    image_size = struct.unpack('<L', image_size_data)[0]

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
            mode_data = conn.recv(7).decode('utf-8')  # "CAPTURE" or "DESCRIBE"
            if not mode_data:
                break
            
            print(f"Mode received: {mode_data}")

            # Receive and process the image
            frame = receive_image(conn)
            if frame is None:
                print("Failed to receive image.")
                break

            # Save the image
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.jpg")
            cv2.imwrite(image_path, frame)
            print(f"Image saved: {image_path}")

            if mode_data == "CAPTURE":
                # Apply OCR and save extracted text
                text = apply_ocr(image_path)
                text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
                with open(text_file_path, "w") as f:
                    f.write(text)
                print(f"Extracted text saved: {text_file_path}")

                # Convert text to speech and save .wav file
                wav_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.wav")
                text_to_speech(text, wav_file_path)
                print(f"TTS saved: {wav_file_path}")

                # Send the .wav file back to the Raspberry Pi
                with open(wav_file_path, "rb") as f:
                    audio_data = f.read()
                
                conn.sendall(struct.pack('<L', len(audio_data)))  # Send audio file size
                conn.sendall(audio_data)  # Send audio file content
                print("WAV file sent back to host.")

            elif mode_data == "DESCRIBE":
                pass  # Placeholder for future development

    except Exception as e:
        print(f"Error: {e}")

    finally:
        conn.close()

