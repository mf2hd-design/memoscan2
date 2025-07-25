import os
import base64
import io
import logging
from flask import Flask, render_template, send_file
from flask_socketio import SocketIO

from scanner import run_full_scan_stream, SHARED_CACHE

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

socketio = SocketIO(app, async_mode='gevent', logger=os.getenv("LOG_LEVEL", "INFO") == "DEBUG")

logger = logging.getLogger("app")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

@app.route("/")
def index():
    return render_template("index.html")

def pad_b64(s: str) -> str:
    missing = len(s) % 4
    if missing:
        s += "=" * (4 - missing)
    return s

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    """Serve the cached screenshot as PNG (we stored JPEG but that's fine to serve as JPEG)."""
    b64_data = SHARED_CACHE.get(image_id)
    if not b64_data:
        return "Screenshot not found", 404
    try:
        # It's JPEG, serve as such
        image_bytes = base64.b64decode(pad_b64(b64_data), validate=False)
        return send_file(io.BytesIO(image_bytes), mimetype='image/jpeg')
    except Exception as e:
        logger.error("Failed to decode screenshot %s: %s", image_id, e)
        return "Invalid screenshot", 500

def run_scan_in_background(url):
    logger.info("[Background Task] Starting scan for: %s", url)
    try:
        for data_object in run_full_scan_stream(url, SHARED_CACHE):
            socketio.emit('scan_update', data_object)
    except Exception as e:
        logger.exception("[Background Task CRITICAL ERROR] The task failed: %s", e)
        socketio.emit('scan_update', {'type': 'error', 'message': f'A critical background error occurred: {e}'})
    finally:
        logger.info("[Background Task] Finished scan for: %s", url)

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('start_scan')
def handle_scan_request(json_data):
    url = json_data.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return
    socketio.start_background_task(target=run_scan_in_background, url=url)
    socketio.emit('scan_update', {'type': 'status', 'message': 'Scan request received, process starting in background.'})

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
