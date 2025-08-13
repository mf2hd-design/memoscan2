import os
import uuid
from flask import Flask, render_template, send_file
from flask_socketio import SocketIO
import base64
import io

# Import the main scanner function
from scanner import run_full_scan_stream

app = Flask(__name__)
# CORRECTED: The key should be all uppercase.
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

# In-memory cache for storing screenshots temporarily.
screenshot_cache = {}

# CORRECTED: Removed the 'message_queue' argument. This is the critical fix.
# This configures SocketIO for a standalone gevent server.
socketio = SocketIO(app, async_mode='gevent')

@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    """This is the new HTTP endpoint to serve the cached screenshot."""
    b64_data = screenshot_cache.get(image_id)
    if b64_data:
        image_bytes = base64.b64decode(b64_data)
        return send_file(io.BytesIO(image_bytes), mimetype='image/png')
    else:
        return "Screenshot not found", 404

def run_scan_in_background(url):
    """
    This helper function runs the full scan and emits results over the WebSocket.
    """
    print(f"[Background Task] Starting scan for: {url}")
    try:
        for data_object in run_full_scan_stream(url, screenshot_cache):
            socketio.emit('scan_update', data_object)
    except Exception as e:
        print(f"[Background Task CRITICAL ERROR] The task failed: {e}")
        socketio.emit('scan_update', {'type': 'error', 'message': f'A critical background error occurred: {e}'})
    finally:
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
    """Handles the 'start_scan' event from the browser."""
    url = json_data.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return
    
    # Start the long-running process as a background task managed by gevent.
    socketio.start_background_task(target=run_scan_in_background, url=url)
    
    socketio.emit('scan_update', {'type': 'status', 'message': 'Scan request received, process starting in background.'})

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
