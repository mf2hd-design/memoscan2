import os
import uuid
from flask import Flask, render_template, send_file, Response
from flask_socketio import SocketIO
import base64
import io

# We need to import the scanner function here to be used in the background task
from scanner import run_full_scan_stream

app = Flask(__name__)
# A secret key is required for Flask sessions, which SocketIO can use.
app.config['SECRET_key'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

# In-memory cache for storing screenshots temporarily.
# A simple dictionary is sufficient for this single-process gevent setup.
screenshot_cache = {}

# Initialize SocketIO, ensuring it uses the Redis message queue for communication
# between the web server and any potential background workers.
socketio = SocketIO(app, async_mode='gevent', message_queue=os.environ.get("REDIS_URL"))

@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    """
    This is the new HTTP endpoint to serve the cached screenshot.
    The browser will call this URL to download the image.
    """
    b64_data = screenshot_cache.get(image_id)
    if b64_data:
        # Decode the base64 string back into binary image data.
        image_bytes = base64.b64decode(b64_data)
        # Use Flask's send_file to return the data with the correct image MIME type.
        return send_file(io.BytesIO(image_bytes), mimetype='image/png')
    else:
        # If the ID is not found, return a 404 error.
        return "Screenshot not found", 404

def run_scan_and_emit(url):
    """
    This helper function contains the logic that will run in the background.
    It iterates through the scanner's generator and emits each result over the WebSocket.
    """
    print(f"[Background Task] Starting scan for: {url}")
    # We pass the screenshot_cache dictionary to the generator so it can store the image.
    for data_object in run_full_scan_stream(url, screenshot_cache):
        socketio.emit('scan_update', data_object)
    print(f"[Background Task] Finished scan for: {url}")

@socketio.on('connect')
def handle_connect():
    """Handles a new client connecting via WebSocket."""
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """Handles a client disconnecting."""
    print('Client disconnected')

@socketio.on('start_scan')
def handle_scan_request(json_data):
    """
    Handles the 'start_scan' event from the browser.
    This function now starts the scan as a background task.
    """
    url = json_data.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return
    
    # This is critical: we start the long-running process as a background task.
    # This immediately frees up the main server process to handle other requests.
    socketio.start_background_task(target=run_scan_and_emit, url=url)
    
    # We can instantly confirm to the user that the task has been received.
    socketio.emit('scan_update', {'type': 'status', 'message': 'Scan request received and queued.'})

# This is used for local development. On Render, Gunicorn runs the app.
if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
