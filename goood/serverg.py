import socket
import cv2
import numpy as np
import struct
import pytesseract
from gtts import gTTS
import os
from PIL import Image
import time
import torch
from transformers import Blip2Processor, Blip2ForConditionalGeneration
import requests

# Server Configuration
HOST = '192.168.157.52'
PORT = 8000

# Directories for storing results
output_text_dir = "./TextOutputs/"
output_audio_dir = "./AudioOutputs/"

# Ensure directories exist
os.makedirs(output_text_dir, exist_ok=True)
os.makedirs(output_audio_dir, exist_ok=True)

# Initialize BLIP-2 model and processor
print("Loading BLIP-2 model...")
processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
model = Blip2ForConditionalGeneration.from_pretrained(
    "Salesforce/blip2-opt-2.7b", 
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
)
if torch.cuda.is_available():
    model.to("cuda")
print("BLIP-2 model loaded successfully")

def text_to_speech(text, filename):
    """Convert text to speech and save as an .mp3 file"""
    tts = gTTS(text=text, lang="en")
    tts.save(filename)

def apply_ocr(image_path):
    """Perform OCR on an image and return the extracted text"""
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text.strip()

def describe_image(image_path):
    """Use BLIP-2 to generate a description of the image"""
    try:
        # Load and preprocess the image
        image = Image.open(image_path)
        inputs = processor(image, return_tensors="pt")
        
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        # Generate image description
        generated_ids = model.generate(
            **inputs,
            max_length=50,
            num_beams=5,
            min_length=10,
            temperature=0.7,
            do_sample=True
        )
        
        # Decode the generated text
        description = processor.decode(generated_ids[0], skip_special_tokens=True)
        return f"This image shows {description}"
    except Exception as e:
        print(f"Error in image description: {e}")
        return "I'm sorry, but I couldn't generate a description for this image."

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

def process_and_send_audio(text, conn, mode_data, timestamp):
    """Process text to audio and send it back to client"""
    # Convert text to speech and save as .mp3 file
    mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
    text_to_speech(text, mp3_file_path)
    print(f"TTS saved as MP3: {mp3_file_path}")
    
    # Send the .mp3 file back to the Raspberry Pi
    with open(mp3_file_path, "rb") as f:
        audio_data = f.read()
    
    conn.sendall(struct.pack('<L', len(audio_data)))  # Send audio file size
    conn.sendall(audio_data)  # Send audio file content
    print("MP3 file sent back to host.")

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
            mode_data = conn.recv(7).decode('utf-8').strip()  # "CAPTURE" or "DESCRIBE"
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
            
            if mode_data.strip() == "CAPTURE":
                # Apply OCR and save extracted text
                text = apply_ocr(image_path)
                text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
                with open(text_file_path, "w") as f:
                    f.write(text)
                print(f"Extracted text saved: {text_file_path}")
                
                # Process and send audio
                process_and_send_audio(text, conn, mode_data, timestamp)
                
            elif mode_data.strip() == "DESCRIBE":
                # Generate image description using BLIP-2
                description = describe_image(image_path)
                
                # Save description to text file
                text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
                with open(text_file_path, "w") as f:
                    f.write(description)
                print(f"Image description saved: {text_file_path}")
                
                # Process and send audio
                process_and_send_audio(description, conn, mode_data, timestamp)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
