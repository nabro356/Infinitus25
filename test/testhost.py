import io
import socket
import struct
import time
import os
import RPi.GPIO as GPIO
from picamera2 import Picamera2

# GPIO Setup
button_pin = 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Server Configuration
server_ip = '192.68.157.52'
server_port = 8000
client_socket = socket.socket()
client_socket.connect((server_ip, server_port))

# Mode Management
current_mode = "MODE-I"
mode_names = {"MODE-I": "Capture Mode", "MODE-II": "Stream Mode"}

def announce_mode(mode):
    """ Announce the mode name using TTS """
    mode_name = mode_names[mode]
    os.system(f'espeak "{mode_name}"')

def button_callback(channel):
    global current_mode
    # Commented out Mode-II switching
    # current_mode = "MODE-II" if current_mode == "MODE-I" else "MODE-I"
    print(f"Mode: {current_mode}")
    announce_mode(current_mode)
    delete_captured_image()

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
    os.system(f"aplay {wav_file_path}")

def main():
    picam2 = Picamera2()
    config = picam2.create_preview_configuration({"size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    time.sleep(2)  # Camera warm-up

    stream = io.BytesIO()
    
    try:
        while True:
            # Removed Mode-II block
            # Single image mode only
            print("Capturing a single image...")
            picam2.capture_file(stream, format='jpeg')

            # Save the captured image
            image_path = "/home/focus/temp_image.jpg"
            with open(image_path, "wb") as f:
                f.write(stream.getvalue())

            # Send mode
            client_socket.send(current_mode.encode('utf-8'))

            # Send image size and data
            image_size = stream.tell()
            client_socket.send(struct.pack('<L', image_size))
            stream.seek(0)
            client_socket.send(stream.read())

            # Clear the stream
            stream.seek(0)
            stream.truncate()

            # Receive WAV response
            receive_wav()
            time.sleep(2)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        # Send termination signal
        client_socket.send(struct.pack('<L', 0))
        client_socket.close()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
