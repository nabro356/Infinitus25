from flask import Flask, Response
import cv2

app = Flask(__name__)

# Initialize Raspberry Pi Camera
cap = cv2.VideoCapture(0)  # Use Pi Camera

def generate_frames():
    """Continuously capture frames and send them to the Flask server."""
    while True:
        success, frame = cap.read()
        if not success:
            break
        
        # Encode the frame in JPEG format
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        # Yield frame as a multipart response
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """Route to stream video feed."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
