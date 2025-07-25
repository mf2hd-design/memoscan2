import os
import io
import base64

from flask import Flask, render_template, send_file
from flask_socketio import SocketIO

from scanner import run_full_scan_stream, SHARED_CACHE

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

socketio = SocketIO(app, async_mode='gevent')

def _pad_b64(data: str) -> str:
    m = len(data) % 4
    return data + ("=" * (4 - m)) if m else data

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    b64_data = SHARED_CACHE.get(image_id)
    if not b64_data:
        return "Screenshot not found", 404
    try:
        raw = base64.b64decode(_pad_b64(b64_data))
    except Exception:
        return "Invalid base64 screenshot", 500
    # ScrapingBee always returns PNG — but we don't rely on this, we just stream bytes.
    return send_file(io.BytesIO(raw), mimetype='image/png')

def run_scan_in_background(url: str):
    print(f"[Background Task] Starting scan for: {url}")
    try:
        for payload in run_full_scan_stream(url, SHARED_CACHE):
            socketio.emit('scan_update', payload)
    except Exception as e:
        print(f"[Background Task CRITICAL ERROR] {e}")
        socketio.emit('scan_update', {'type': 'error', 'message': f'A critical background error occurred: {e}'})
    finally:
        print(f"[Background Task] Finished scan for: {url}")

@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('start_scan')
def handle_scan_request(json_data):
    url = json_data.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return
    socketio.start_background_task(target=run_scan_in_background, url=url)
    socketio.emit('scan_update', {'type': 'status', 'message': 'Scan request received, process starting in background.'})

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
