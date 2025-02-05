import socket
import cv2
import numpy as np
import struct
import os
import time
import requests
import joblib
import torch
import easyocr
from gtts import gTTS  # Google Text-to-Speech
from facenet_pytorch import InceptionResnetV1, MTCNN
from PIL import Image
from google.cloud import vision

# Server Configuration
HOST = '192.168.157.52'  # Listen on all available network interfaces
PORT = 8000

# Directories for storing results
output_text_dir = "./TextOutputs/"
output_audio_dir = "./AudioOutputs/"

# Ensure directories exist
os.makedirs(output_text_dir, exist_ok=True)
os.makedirs(output_audio_dir, exist_ok=True)

# Initialize EasyOCR
ocr_reader = easyocr.Reader(['en'])

# Google Cloud Vision API Setup
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'vision-api-450017-cbe451515384.json'
client = vision.ImageAnnotatorClient()

# Gemini API Key
GEMINI_API_KEY = 'AIzaSyBjuQHU8GYEPm9Fj0Rrna26-E6zdwXAhLg'

# Load Face Recognition Model
MODEL_SAVE_PATH = "face_recognition_model.pkl"
model_data = joblib.load(MODEL_SAVE_PATH)
classifier = model_data["model"]
label_encoder = model_data["encoder"]

# Load FaceNet and MTCNN
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
facenet_model = InceptionResnetV1(pretrained='vggface2').eval().to(device)
mtcnn = MTCNN(image_size=160, margin=20, keep_all=False)

def text_to_speech(text, filename):
    """Convert text to speech and save as an .mp3 file"""
    tts = gTTS(text=text, lang="en")
    tts.save(filename)

def apply_ocr(image_path):
    """Perform OCR on an image using EasyOCR and return the extracted text"""
    img = cv2.imread(image_path)
    results = ocr_reader.readtext(img)
    extracted_text = " ".join([text for _, text, _ in results])
    return extracted_text.strip()

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

def get_labels_from_image(image_path):
    """Get scene labels using Google Cloud Vision API"""
    with open(image_path, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.label_detection(image=image)

    if response.error.message:
        raise Exception(f'Error: {response.error.message}')

    labels = [label.description for label in response.label_annotations]
    return labels

def extract_embeddings(image_path):
    """Extract FaceNet embeddings from an image"""
    image = Image.open(image_path).convert("RGB")
    face = mtcnn(image)
    if face is not None:
        face = face.unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = facenet_model(face)
        return embedding.cpu().numpy().flatten()
    return None

def recognize_face(embedding):
    """Recognize face using the trained classifier"""
    if embedding is not None:
        probs = classifier.predict_proba([embedding])[0]
        max_prob = max(probs)

        if max_prob < 0.50:  # Threshold
            return "Unknown person", max_prob
        else:
            prediction = np.argmax(probs)
            person_name = label_encoder.inverse_transform([prediction])[0]
            return person_name, max_prob
    else:
        return "No face detected", 0

def describe_scene_with_gemini(labels, image_path, person_name):
    """Generate a scene description using Gemini AI"""
    labels_str = ", ".join(labels)

    if "Paper" in labels_str or "Document" in labels_str:
        extracted_text = apply_ocr(image_path)
        description = f"The scene contains a document. The extracted text is: {extracted_text}"
    else:
        prompt = f"Describe the scene with these words: {labels_str}. Also include '{person_name}' in the response."
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}'
        data = {"contents": [{"parts": [{"text": prompt}]}]}

        response = requests.post(url, json=data)

        if response.status_code == 200:
            response_data = response.json()
            description = response_data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            description = "Error generating scene description."

    return description

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
            mode_data = conn.recv(7).decode('utf-8')
            if not mode_data:
                break
            
            print(f"Mode received: {mode_data}")

            frame = receive_image(conn)
            if frame is None:
                print("Failed to receive image.")
                break

            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.jpg")
            cv2.imwrite(image_path, frame)
            print(f"Image saved: {image_path}")

            if mode_data == "CAPTURE":
                text = apply_ocr(image_path)
                text_file_path = os.path.join(output_text_dir, f"{mode_data}_{timestamp}.txt")
                with open(text_file_path, "w") as f:
                    f.write(text)
                print(f"Extracted text saved: {text_file_path}")

                mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
                text_to_speech(text, mp3_file_path)
                print(f"TTS saved as MP3: {mp3_file_path}")

                with open(mp3_file_path, "rb") as f:
                    audio_data = f.read()
                
                conn.sendall(struct.pack('<L', len(audio_data)))
                conn.sendall(audio_data)
                print("MP3 file sent back to host.")

            elif mode_data == "DESCRIBE":
                labels = get_labels_from_image(image_path)
                embedding = extract_embeddings(image_path)
                person_name, confidence = recognize_face(embedding)

                final_description = describe_scene_with_gemini(labels, image_path, person_name)
                mp3_file_path = os.path.join(output_audio_dir, f"{mode_data}_{timestamp}.mp3")
                text_to_speech(final_description, mp3_file_path)

                with open(mp3_file_path, "rb") as f:
                    audio_data = f.read()
                
                conn.sendall(struct.pack('<L', len(audio_data)))
                conn.sendall(audio_data)
                print("Scene description MP3 sent back.")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        conn.close()
