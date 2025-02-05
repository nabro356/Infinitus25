import socket
import cv2
import numpy as np
import struct
import pytesseract
import pyttsx3
import json
from PIL import Image
#from facenet_pytorch import MTCNN, InceptionResnetV1
#from scipy.spatial.distance import cosine

# FaceNet setup
#mtcnn = MTCNN()
#model = InceptionResnetV1(pretrained='vggface2').eval()

# TTS engine
engine = pyttsx3.init()

# Load saved face embeddings
"""
def load_embeddings(file="objects.json"):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}"""

# Function to convert text to speech
def text_to_speech(text, filename="/home/focus/output.wav"):
    engine.save_to_file(text, filename)
    engine.runAndWait()

# Function for OCR on image
def apply_ocr(image_path):
    img = Image.open(image_path)
    return pytesseract.image_to_string(img)
"""
# Function for face recognition
def recognize_faces(frame, saved_embeddings):
    faces = mtcnn.detect(frame)
    face_names = []
    for face in faces[0]:
        aligned_face = mtcnn.align(frame, face)
        embedding = model(aligned_face.unsqueeze(0)).detach().numpy().flatten()

        best_match_name = "Unknown"
        best_match_distance = float("inf")
        for name, saved_embedding in saved_embeddings.items():
            distance = cosine(embedding, saved_embedding)
            if distance < best_match_distance:
                best_match_name = name
                best_match_distance = distance
        
        face_names.append(f"{best_match_name} is in front of you.")
    return face_names
"""

def main():
    # Setup
    HOST = '192.168.157.52'
    PORT = 8000
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1)
    print(f"Listening on port {PORT}...")

    while True:
        conn, addr = server_socket.accept()
        print(f"Connected by {addr}")
        
        #saved_embeddings = load_embeddings()

        try:
            while True:
                # Receive mode
                mode_bytes = conn.recv(6)  # MODE-I or MODE-II
                if not mode_bytes:
                    break
                mode = mode_bytes.decode('utf-8')

                # Receive image size
                size_data = conn.recv(4)
                if not size_data:
                    break
                image_size = struct.unpack('<L', size_data)[0]
                
                # Termination check
                if image_size == 0:
                    break

                # Receive image data
                image_data = b""
                while len(image_data) < image_size:
                    chunk = conn.recv(min(4096, image_size - len(image_data)))
                    if not chunk:
                        break
                    image_data += chunk

                # Process image
                frame_data = np.frombuffer(image_data, dtype=np.uint8)
                frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    if mode == "MODE-I":
                        # Save image for OCR
                        image_path = "/home/focus/temp_image.jpg"
                        cv2.imwrite(image_path, frame)
                        
                        # Perform OCR
                        text = apply_ocr(image_path)
                        
                        # Convert text to speech
                        text_to_speech(text)
                        
                        # Send WAV file back
                        with open("/home/focus/output.wav", "rb") as f:
                            wav_data = f.read()
                            conn.sendall(struct.pack('<L', len(wav_data)))
                            conn.sendall(wav_data)
                    
                    elif mode == "MODE-II":
                        # Future implementation for continuous video processing
                        # This could include more advanced scene recognition, 
                        # face detection, etc.
                        pass

        except Exception as e:
            print(f"Error processing connection: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    main()
