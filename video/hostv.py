import io
import socket
import struct
import time
import os
import threading
import RPi.GPIO as GPIO
from picamera2 import Picamera2
import subprocess

# GPIO Setup
button_pin = 2  # GPIO pin for mode switching
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '192.168.157.52'  # Replace with actual server IP
server_port = 8000

# Mode Management
modes = ["CAPTURE", "DESCRIBE"]
current_mode_index = 0  # Start in Mode-I (CAPTURE)
running = threading.Event()  # Control flag for auto-capture thread

# Directories for saving images & output files
image_dir = "/home/pizero/ProjectImages/"
output_dir = "/home/pizero/ProjectOutput/"
os.makedirs(image_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# Initialize Picamera2
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)  # Allow camera to warm up

def toggle_mode(channel):
    """Toggle between CAPTURE and DESCRIBE modes."""
    global current_mode_index
    current_mode_index = (current_mode_index + 1) % 2  # Toggle between 0 (CAPTURE) and 1 (DESCRIBE)
    current_mode = modes[current_mode_index]
    print(f"[TOGGLE] Mode changed to: {current_mode}")

    if current_mode == "CAPTURE":
        running.clear()  # Stop auto-capture
        print("[MODE-I] Capturing a single image...")
        capture_and_send_image("CAPTURE")  
    else:
        print("[MODE-II] Starting auto capture every 30s...")
        running.set()
        threading.Thread(target=auto_capture_describe, daemon=True).start()

GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=toggle_mode, bouncetime=500)

def receive_mp3():
    """Receive and play the MP3 file from the server."""
    try:
        size_data = client_socket.recv(4)
        if not size_data or len(size_data) < 4:
            print("[MP3] No valid MP3 file size received.")
            return
        
        mp3_size = struct.unpack('<L', size_data)[0]
        if mp3_size == 0:
            print("[MP3] No MP3 file received.")
            return

        mp3_path = os.path.join(output_dir, "output.mp3")
        with open(mp3_path, "wb") as f:
            remaining_size = mp3_size
            while remaining_size > 0:
                data = client_socket.recv(min(1024, remaining_size))
                if not data:
                    break
                f.write(data)
                remaining_size -= len(data)

        print(f"[MP3] File saved: {mp3_path}")
        subprocess.Popen(["mpg321", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    except Exception as e:
        print(f"[MP3] Error receiving MP3 file: {e}")

def capture_and_send_image(mode):
    """Capture an image and send it to the server."""
    print(f"[{mode}] Capturing and sending image...")

    try:
        client_socket = socket.socket()
        client_socket.connect((server_ip, server_port))
        connection = client_socket.makefile('wb')

        # Generate filename
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(image_dir, f"{mode}_{timestamp}.jpg")

        # Capture Image
        picam2.capture_file(image_path)
        print(f"[{mode}] Image saved: {image_path}")

        # Read Image
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Send Mode Info
        connection.write(mode.ljust(7).encode('utf-8'))
        connection.flush()

        # Send Image Size
        connection.write(struct.pack('<L', len(image_data)))
        connection.flush()

        # Send Image Data
        connection.write(image_data)
        connection.flush()

        # Receive and Play MP3
        print(f"[{mode}] Waiting for MP3 response...")
        receive_mp3()

    except Exception as e:
        print(f"[{mode}] Error in capture/send: {e}")

    finally:
        connection.write(struct.pack('<L', 0))  # Termination signal
        connection.close()
        client_socket.close()

def auto_capture_describe():
    """Automatically captures and sends an image every 30 seconds in DESCRIBE mode."""
    while running.is_set():
        print("[MODE-II] Auto-capturing image...")
        capture_and_send_image("DESCRIBE")
        for _ in range(30):  # Wait for 30 seconds in steps
            if not running.is_set():
                print("[MODE-II] Stopping auto-capture...")
                return
            time.sleep(1)

try:
    print("Waiting for button press...")
    while True:
        time.sleep(0.1)  # Keep the script running

finally:
    GPIO.cleanup()
