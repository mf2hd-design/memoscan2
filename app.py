import os
import base64
import io
from flask import Flask, render_template, send_file
from flask_socketio import SocketIO

# Import ONLY the runner from scanner
from scanner import run_full_scan_stream

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

# In-memory cache for storing screenshots temporarily.
screenshot_cache = {}

# Standalone gevent SocketIO (no message_queue)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    b64_data = screenshot_cache.get(image_id)
    if not b64_data:
        return "Screenshot not found", 404
    try:
        # add padding if needed to avoid Incorrect padding errors
        missing = len(b64_data) % 4
        if missing:
            b64_data += "=" * (4 - missing)
        image_bytes = base64.b64decode(b64_data)
    except Exception as e:
        return f"Invalid screenshot data: {e}", 500
    return send_file(io.BytesIO(image_bytes), mimetype='image/png')

def run_scan_in_background(url):
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
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_scan')
def handle_scan_request(json_data):
    url = json_data.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return

    socketio.start_background_task(target=run_scan_in_background, url=url)
    socketio.emit('scan_update', {'type': 'status', 'message': 'Scan request received, process starting in background.'})

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
