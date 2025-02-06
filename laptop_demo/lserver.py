import cv2
import torch
import numpy as np
import joblib
from PIL import Image
from facenet_pytorch import InceptionResnetV1, MTCNN
import google.generativeai as genai  # Gemini API

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyCEf0o9rf35KymGiWStK3kBg2G8lHCkF1s"  # Replace with your Gemini API key
genai.configure(api_key=GEMINI_API_KEY)

# Load FaceNet model and classifier
MODEL_SAVE_PATH = "face_recognition_model.pkl"
model_data = joblib.load(MODEL_SAVE_PATH)
classifier = model_data["model"]
label_encoder = model_data["encoder"]

# Load FaceNet and MTCNN
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
facenet_model = InceptionResnetV1(pretrained="vggface2").eval().to(device)
mtcnn = MTCNN(image_size=160, margin=20, keep_all=False)

# Raspberry Pi video stream URL
VIDEO_URL = "http://192.168.1.100:5000/video_feed"  # Change to your Raspberry Pi's IP

def extract_embeddings(image):
    """Extract embeddings using FaceNet from an image frame."""
    face = mtcnn(image)
    if face is not None:
        face = face.unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = facenet_model(face)
        return embedding.cpu().numpy().flatten()
    return None

def recognize_face(embedding):
    """Recognize the face by comparing embeddings with the classifier."""
    if embedding is not None:
        probs = classifier.predict_proba([embedding])[0]
        max_prob = max(probs)

        if max_prob < 0.50:
            return "Unknown person", max_prob
        else:
            prediction = np.argmax(probs)
            person_name = label_encoder.inverse_transform([prediction])[0]
            return person_name, max_prob
    else:
        return "No face detected", 0

def describe_scene(image):
    """Use Gemini API to generate a scene description."""
    try:
        _, buffer = cv2.imencode(".jpg", image)
        response = genai.generate_text(
            model="gemini-pro-vision",
            prompts=["Describe this scene in a simple sentence."],
            input_data={"image_bytes": buffer.tobytes()}
        )
        return response.text
    except Exception as e:
        print(f"Error using Gemini API: {e}")
        return "Scene description unavailable."

# Start video stream processing
cap = cv2.VideoCapture(VIDEO_URL)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Convert frame to RGB format for FaceNet
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb_frame)

    # Extract embeddings and recognize face
    embedding = extract_embeddings(image)
    person_name, confidence = recognize_face(embedding)

    # Generate scene description using Gemini API
    scene_description = describe_scene(frame)

    # Overlay results on frame
    cv2.putText(frame, f"{person_name} is here", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(frame, f"Scene: {scene_description}", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)

    cv2.imshow("Face Recognition & Scene Description", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
