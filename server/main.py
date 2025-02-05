import socket
import cv2
import numpy as np
import struct, io
import pytesseract
import pyttsx3
import time
import json
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1
from scipy.spatial.distance import cosine  # For comparing embeddings


# FaceNet setup
mtcnn = MTCNN()
model = InceptionResnetV1(pretrained='vggface2').eval()

# Load saved face embeddings from objects.json
def load_embeddings(file="objects.json"):
    try:
        with open(file, "r") as f:
            embeddings_data = json.load(f)
        return embeddings_data
    except FileNotFoundError:
        return {}

# Save face embeddings to objects.json
def save_embeddings(file="objects.json", embeddings_data={}):
    with open(file, "w") as f:
        json.dump(embeddings_data, f, indent=4)

# TTS engine
engine = pyttsx3.init()

# Setup
HOST = ''
PORT = 8000
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"Listening on port {PORT}...")

# Function to convert text to speech and save it as a .wav file
def text_to_speech(text, filename="/home/focus/output.wav"):
    engine.save_to_file(text, filename)
    engine.runAndWait()

# Function for OCR on image
def apply_ocr(image_path):
    img = Image.open(image_path)
    text = pytesseract.image_to_string(img)
    return text

# Function for face recognition using embeddings
def recognize_faces(frame, saved_embeddings):
    faces = mtcnn.detect(frame)
    face_names = []
    for face in faces[0]:
        aligned_face = mtcnn.align(frame, face)
        embedding = model(aligned_face.unsqueeze(0)).detach().numpy().flatten()

        # Compare embeddings with saved embeddings using cosine similarity
        best_match_name = "Unknown"
        best_match_distance = float("inf")
        for name, saved_embedding in saved_embeddings.items():
            distance = cosine(embedding, saved_embedding)
            if distance < best_match_distance:
                best_match_name = name
                best_match_distance = distance
        
        face_names.append(f"{best_match_name} is in front of you.")
    return face_names

# Main server loop
while True:
    conn, addr = server_socket.accept()
    print(f"Connected by {addr}")
    run_server = True

    # Load saved embeddings from objects.json
    saved_embeddings = load_embeddings()

    try:
        while run_server:
            header = conn.recv(5)  # Read the message type and length
            if not header:
                print("No header received, closing connection.")
                run_server = False
                conn.close()
                break
            message_type, message_length = struct.unpack('<BI', header)

            message_data = b""
            while len(message_data) < message_length:
                packet = conn.recv(message_length - len(message_data))
                if not packet:
                    break
                message_data += packet

            if message_type == 0:  # Mode message
                mode = message_data.decode('utf-8')
            elif message_type == 1:  # Image data
                frame_data = np.frombuffer(message_data, dtype=np.uint8)
                frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                if frame is not None:
                    if mode == "MODE-I":
                        # Apply OCR to the image
                        image_path = "/home/focus/temp_image.jpg"
                        cv2.imwrite(image_path, frame)  # Save the image for OCR processing
                        text = apply_ocr(image_path)

                        # Convert the extracted text to speech and send back as .wav
                        text_to_speech(text)
                        with open("/home/focus/output.wav", "rb") as f:
                            audio_data = f.read()
                            conn.sendall(audio_data)

                    elif mode == "MODE-II":
                        # Apply Gemini API for scene description (Placeholder)
                        scene_description = "Detected a car in the frame."  # Replace with actual Gemini API call

                        # Apply FaceNet for face recognition
                        face_names = recognize_faces(frame, saved_embeddings)
                        description = f"{scene_description} {' '.join(face_names)}"

                        # Convert scene description to speech and send back as .wav
                        text_to_speech(description)
                        with open("/home/focus/output.wav", "rb") as f:
                            audio_data = f.read()
                            conn.sendall(audio_data)

                else:
                    print("Failed to decode frame.")
    finally:
        pass
