import io
import socket
import struct
import time
import os  # For running TTS commands and file deletion
import RPi.GPIO as GPIO
from picamera2 import Picamera2

# GPIO Setup
button_pin = 2  # Changed to GPIO pin 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '0.0.0.0'  
server_port = 8000
client_socket = socket.socket()
client_socket.connect((server_ip, server_port))
connection = client_socket.makefile('wb')

# Mode Management
current_mode = "MODE-I"  # Default to Capture Mode
mode_names = {"MODE-I": "Capture Mode", "MODE-II": "Stream Mode"}

def announce_mode(mode):
    """ Announce the mode name using TTS """
    mode_name = mode_names[mode]
    os.system(f'espeak "{mode_name}"')  # Converts text to speech

def button_callback(channel):
    global current_mode
    if current_mode == "MODE-I":
        current_mode = "MODE-II"
        delete_captured_image()  # Delete captured image when switching to Mode-II
    else:
        current_mode = "MODE-I"
    print(f"Mode changed to: {current_mode}")
    announce_mode(current_mode)  # Announce the mode name

GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=button_callback, bouncetime=300)

def delete_captured_image():
    """ Delete the captured image if it exists """
    image_path = "/home/focus/temp_image.jpg"
    if os.path.exists(image_path):
        os.remove(image_path)
        print(f"Deleted captured image: {image_path}")

def receive_wav():
    """ Receive a .wav file from the server, save it, and play it. """
    wav_size = struct.unpack('<L', client_socket.recv(4))[0]
    if wav_size == 0:
        print("No WAV file received")
        return

    wav_data = client_socket.recv(wav_size)
    wav_file_path = "/home/focus/output.wav"
    with open(wav_file_path, "wb") as f:
        f.write(wav_data)
    print("Received and saved output.wav")

    # Play the received .wav file using aplay
    os.system(f"aplay {wav_file_path}")

try:
    picam2 = Picamera2()
    config = picam2.create_preview_configuration({"size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # Camera warm-up

    stream = io.BytesIO()
    
    while True:
        if current_mode == "MODE-I":
            # Capture a single image and send it
            print("Capturing a single image...")
            picam2.capture_file(stream, format='jpeg')

            # Save the captured image
            image_path = "/home/focus/temp_image.jpg"
            with open(image_path, "wb") as f:
                f.write(stream.getvalue())

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

            # Clear the stream
            stream.seek(0)
            stream.truncate()

            # Receive and save WAV response
            receive_wav()
            time.sleep(2)  # Wait before capturing the next image

        elif current_mode == "MODE-II":
            # Continuous video streaming
            print("Streaming video frames...")
            for _ in range(10):  # Limit to 10 frames for testing; remove for continuous
                picam2.capture_file(stream, format='jpeg')

                # Send mode information
                connection.write(current_mode.encode('utf-8'))
                connection.flush()

                # Send frame size
                connection.write(struct.pack('<L', stream.tell()))
                connection.flush()

                # Send frame data
                stream.seek(0)
                connection.write(stream.read())
                connection.flush()

                # Clear the stream
                stream.seek(0)
                stream.truncate()

                # Receive and save WAV response for each frame
                receive_wav()

finally:
    connection.write(struct.pack('<L', 0))  # Send termination signal
    connection.close()
    client_socket.close()
    GPIO.cleanup()

