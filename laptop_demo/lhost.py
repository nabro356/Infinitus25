import socket
import cv2
import struct
import pickle

# Raspberry Pi Server Configuration
SERVER_IP = "192.168.157.52"  # Change this to your laptop's IP
PORT = 8000

# Initialize Pi Camera
cap = cv2.VideoCapture(0)  # Use Pi Camera

# Create a socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.connect((SERVER_IP, PORT))

print("Streaming video to client...")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Encode the frame
        data = pickle.dumps(frame)
        size = struct.pack("L", len(data))

        # Send the size and data
        server_socket.sendall(size + data)

except Exception as e:
    print(f"Error: {e}")

finally:
    cap.release()
    server_socket.close()
