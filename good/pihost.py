import io
import socket
import struct
import time
import os
import RPi.GPIO as GPIO
from picamera2 import Picamera2

# GPIO Setup
button_pin = 2  # Changed to GPIO pin 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '192.168.157.52'  # Replace with your server's actual IP
server_port = 8000
client_socket = socket.socket()
client_socket.connect((server_ip, server_port))
connection = client_socket.makefile('wb')

# Mode Management
current_mode = "CAPTURE"  # Default mode
mode_names = ["CAPTURE", "DESCRIBE"]

# Directories for saving images & output files
image_dir = "/home/pizero/ProjectImages/"
output_dir = "/home/pizero/ProjectOutput/"

# Ensure directories exist
os.makedirs(image_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

def button_callback(channel):
    """Toggle between CAPTURE and DESCRIBE modes"""
    global current_mode
    current_mode = "DESCRIBE" if current_mode == "CAPTURE" else "CAPTURE"
    print(f"Mode changed to: {current_mode}")

GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=button_callback, bouncetime=300)

def receive_mp3():
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

        # Play the MP3 file using mpg321
        os.system(f"mpg321 {mp3_path}")

    except Exception as e:
        print(f"Error receiving MP3 file: {e}")

try:
    picam2 = Picamera2()
    config = picam2.create_still_configuration(main={"size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # Allow camera to warm up

    while True:
        # Generate unique filename for each image
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(image_dir, f"{current_mode}_{timestamp}.jpg")

        # Capture image and save locally
        picam2.capture_file(image_path)
        print(f"Image saved: {image_path}")

        # Read the saved image
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Send mode information (Ensure it's always 7 bytes for consistency)
        mode_bytes = current_mode.ljust(7).encode('utf-8')  # Ensure it is always 7 bytes
        connection.write(mode_bytes)
        connection.flush()

        # Send image size
        connection.write(struct.pack('<L', len(image_data)))
        connection.flush()

        # Send image data
        connection.write(image_data)
        connection.flush()

        # Receive and play the MP3 response
        receive_mp3()

finally:
    connection.write(struct.pack('<L', 0))  # Send termination signal
    connection.close()
    client_socket.close()
    GPIO.cleanup()
