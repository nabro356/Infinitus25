import io
import socket
import struct
import time
import os
import threading
import RPi.GPIO as GPIO
from picamera2 import Picamera2

# GPIO Setup
button_pin = 2  # Using GPIO pin 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '192.168.157.52'  # Replace with actual server IP
server_port = 8000

# Mode Management
modes = ["CAPTURE", "DESCRIBE"]  # Mode-I and Mode-II
current_mode_index = 0  # Start in CAPTURE mode

# Directories for saving images & output files
image_dir = "/home/pizero/ProjectImages/"
output_dir = "/home/pizero/ProjectOutput/"

# Ensure directories exist
os.makedirs(image_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# Initialize Picamera2
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)  # Allow camera to warm up

def toggle_mode(channel):
    """Toggle between CAPTURE and DESCRIBE modes"""
    global current_mode_index
    
    current_mode_index = (current_mode_index + 1) % 2  # 0 -> 1 -> 0 (CAPTURE -> DESCRIBE -> CAPTURE)
    current_mode = modes[current_mode_index]
    print(f"Mode changed to: {current_mode}")
    
    capture_and_send_image(current_mode)

GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=toggle_mode, bouncetime=300)

def receive_mp3(client_socket):
    """Receive, save, and play the .mp3 file from the server"""
    try:
        size_data = client_socket.recv(4)
        if not size_data or len(size_data) < 4:
            print("No valid MP3 file size received.")
            return
        
        mp3_size = struct.unpack('<L', size_data)[0]
        if mp3_size == 0:
            print("No MP3 file received")
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

        print(f"MP3 file saved: {mp3_path}")
        os.system(f"mpg321 {mp3_path}")
    except Exception as e:
        print(f"Error receiving MP3 file: {e}")

def capture_and_send_image(mode):
    """Capture an image and send it to the server"""
    try:
        client_socket = socket.socket()
        client_socket.connect((server_ip, server_port))
        connection = client_socket.makefile('wb')

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(image_dir, f"{mode}_{timestamp}.jpg")
        
        picam2.capture_file(image_path)
        print(f"Image saved: {image_path}")
        
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        connection.write(mode.ljust(7).encode('utf-8'))
        connection.flush()
        connection.write(struct.pack('<L', len(image_data)))
        connection.flush()
        connection.write(image_data)
        connection.flush()
        
        receive_mp3(client_socket)
    except Exception as e:
        print(f"Error in capturing/sending image: {e}")
    finally:
        connection.write(struct.pack('<L', 0))
        connection.close()
        client_socket.close()

try:
    print("Waiting for button press...")
    while True:
        time.sleep(0.1)
finally:
    GPIO.cleanup()
