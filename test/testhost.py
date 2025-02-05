import io
import socket
import struct
import time
import os
import picamera
import RPi.GPIO as GPIO

# GPIO Setup
button_pin = 2  # Changed to GPIO pin 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '192.168.157.52'  
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

def receive_wav():
    """Receive and save the .wav file from the server"""
    wav_size = struct.unpack('<L', client_socket.recv(4))[0]
    if wav_size == 0:
        print("No WAV file received")
        return
    
    wav_path = os.path.join(output_dir, "output.wav")
    with open(wav_path, "wb") as f:
        remaining_size = wav_size
        while remaining_size > 0:
            data = client_socket.recv(min(1024, remaining_size))
            if not data:
                break
            f.write(data)
            remaining_size -= len(data)

    print(f"WAV file saved: {wav_path}")

try:
    with picamera.PiCamera() as camera:
        camera.resolution = (640, 480)
        camera.framerate = 24
        time.sleep(2)  # Allow camera to warm up
        
        stream = io.BytesIO()

        for _ in camera.capture_continuous(stream, 'jpeg', use_video_port=True):
            # Generate unique filename for each image
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            image_path = os.path.join(image_dir, f"{current_mode}_{timestamp}.jpg")

            # Save the image locally
            with open(image_path, "wb") as f:
                f.write(stream.getvalue())
            print(f"Image saved: {image_path}")

            # Send mode information
            connection.write(current_mode.encode('utf-8'))
            connection.flush()

            # Send image size
            connection.write(struct.pack('<L', stream.tell()))
            connection.flush()

            # Send image data
            stream.seek(0)
            connection.write(stream.read())
            connection.flush()

            # Clear the stream buffer
            stream.seek(0)
            stream.truncate()

            # Receive and save the WAV response
            receive_wav()

finally:
    connection.write(struct.pack('<L', 0))  # Send termination signal
    connection.close()
    client_socket.close()
    GPIO.cleanup()
