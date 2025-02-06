import io
import socket
import struct
import time
import os
import RPi.GPIO as GPIO
from picamera2 import Picamera2
from google.oauth2 import service_account
from googleapiclient.discovery import build

# **Google Drive API Setup**
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = '/home/pizero/southern-shade-450017-n1-51653cac7517.json'  # Replace with your service account JSON file
drive_service = build('drive', 'v3', credentials=service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES))

# Google Drive Folder IDs (Replace with actual IDs)
IMAGE_FOLDER_ID = "1IqwZ7rO690pPITRP5YTH1QWPh7Ip9VY2"
MP3_FOLDER_ID = "1IqwZ7rO690pPITRP5YTH1QWPh7Ip9VY2"

# **GPIO Setup**
button_pin = 2
GPIO.setmode(GPIO.BCM)
GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# **Server Configuration**
server_ip = '192.168.157.52'  
server_port = 8000

# **Mode Management**
current_mode = "CAPTURE"
mode_names = ["CAPTURE", "DESCRIBE"]

# **Directories for saving images & output files**
image_dir = "/home/pizero/ProjectImages/"
output_dir = "/home/pizero/ProjectOutput/"

# **Ensure directories exist**
os.makedirs(image_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# **Initialize Picamera2**
picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480)})
picam2.configure(config)
picam2.start()
time.sleep(2)  # Allow camera to warm up

def toggle_mode(channel):
    """Toggle between CAPTURE and DESCRIBE modes"""
    global current_mode
    current_mode = "DESCRIBE" if current_mode == "CAPTURE" else "CAPTURE"
    print(f"Mode changed to: {current_mode}")

    if current_mode == "CAPTURE":
        capture_and_send_image()
    elif current_mode == "DESCRIBE":
        upload_image_to_drive()

GPIO.add_event_detect(button_pin, GPIO.FALLING, callback=toggle_mode, bouncetime=300)

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

def capture_and_send_image():
    """Capture an image and send it to the server"""
    global client_socket, connection
    
    try:
        client_socket = socket.socket()
        client_socket.connect((server_ip, server_port))
        connection = client_socket.makefile('wb')

        # Generate unique filename for each image
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(image_dir, f"{current_mode}_{timestamp}.jpg")

        # Capture image and save locally
        picam2.capture_file(image_path)
        print(f"Image saved: {image_path}")

        # Read the saved image
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Send mode information
        mode_bytes = current_mode.ljust(7).encode('utf-8')
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

    except Exception as e:
        print(f"Error in capturing/sending image: {e}")

    finally:
        connection.write(struct.pack('<L', 0))  # Send termination signal
        connection.close()
        client_socket.close()

def upload_image_to_drive():
    """Upload an image every 30 seconds to Google Drive"""
    while current_mode == "DESCRIBE":
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        image_path = os.path.join(image_dir, f"DESCRIBE_{timestamp}.jpg")

        # Capture and save the image
        picam2.capture_file(image_path)
        print(f"Image saved for upload: {image_path}")

        # Upload to Google Drive
        file_metadata = {'name': os.path.basename(image_path), 'parents': [IMAGE_FOLDER_ID]}
        media = drive_service.files().create(body=file_metadata, media_body=image_path).execute()
        print(f"Uploaded {image_path} to Google Drive.")

        # Wait 30 seconds before next upload
        time.sleep(30)

        # Fetch the latest MP3 file from Drive
        fetch_latest_mp3_from_drive()

def fetch_latest_mp3_from_drive():
    """Fetch the latest MP3 file from Google Drive and play it"""
    results = drive_service.files().list(q=f"'{MP3_FOLDER_ID}' in parents and mimeType='audio/mpeg'", 
                                         orderBy="createdTime desc", pageSize=1).execute()
    files = results.get('files', [])

    if not files:
        print("No MP3 file found in Google Drive.")
        return

    latest_mp3 = files[0]  # Get the most recent MP3 file
    mp3_path = os.path.join(output_dir, latest_mp3['name'])
    
    # Download the latest MP3 file
    request = drive_service.files().get_media(fileId=latest_mp3['id'])
    with open(mp3_path, 'wb') as f:
        f.write(request.execute())
    
    print(f"Downloaded latest MP3 file: {mp3_path}")

    # Play the MP3 file
    os.system(f"mpg321 {mp3_path}")

try:
    print("Waiting for button press to capture an image...")
    while True:
        time.sleep(0.1)  # Keep the script running

finally:
    GPIO.cleanup()
