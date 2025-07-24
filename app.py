import os
import uuid
import base64
import io
from flask import Flask, render_template, send_file
from flask_socketio import SocketIO
from typing import Any, Dict

# Import the main scanner function AND the shared cache
from scanner import run_full_scan_stream, SHARED_CACHE

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "a-very-secret-key-that-should-be-changed")

# Keep your SocketIO setup (WebSockets)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

# Backward compatibility alias so existing code still references `screenshot_cache`
# but everything is actually stored in SHARED_CACHE used by scanner.py.
screenshot_cache: Dict[str, Any] = SHARED_CACHE

@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.route('/screenshot/<image_id>')
def get_screenshot(image_id):
    """
    Serve screenshots from the in-memory cache.

    NEW format (recommended):
      screenshot_cache[image_id] = {"mime": "image/png", "bytes": <raw bytes>}

    LEGACY formats we still gracefully handle:
      - raw base64 string (no data: header) -> treated as PNG
      - data URI string "data:image/png;base64,...."
    """
    item = screenshot_cache.get(image_id)
    if item is None:
        return "Screenshot not found", 404

    # Modern format: dict with raw bytes & mime
    if isinstance(item, dict) and "bytes" in item and "mime" in item:
        return send_file(io.BytesIO(item["bytes"]), mimetype=item["mime"])

    # Legacy: data URI string
    if isinstance(item, str) and item.startswith("data:"):
        try:
            header, b64 = item.split(",", 1)
            mime = header.split(";")[0].split(":")[1]
            b64 = b64.strip().replace("\n", "")
            missing = len(b64) % 4
            if missing:
                b64 += "=" * (4 - missing)
            image_bytes = base64.b64decode(b64)
            return send_file(io.BytesIO(image_bytes), mimetype=mime)
        except Exception as e:
            return f"Failed to decode legacy data URI: {e}", 500

    # Legacy: plain base64 PNG
    if isinstance(item, str):
        try:
            b64 = item.strip().replace("\n", "")
            missing = len(b64) % 4
            if missing:
                b64 += "=" * (4 - missing)
            image_bytes = base64.b64decode(b64)
            return send_file(io.BytesIO(image_bytes), mimetype='image/png')
        except Exception as e:
            return f"Failed to decode legacy base64: {e}", 500

    return "Unrecognized screenshot format", 500


def run_scan_in_background(url: str):
    """
    Run the full scan and emit results over the WebSocket.
    Uses the shared cache so screenshots are stored as raw bytes+mime.
    """
    print(f"[Background Task] Starting scan for: {url}")
    try:
        for data_object in run_full_scan_stream(url, screenshot_cache):
            # Stream each event to the frontend
            socketio.emit('scan_update', data_object)
    except Exception as e:
        print(f"[Background Task CRITICAL ERROR] The task failed: {e}")
        socketio.emit('scan_update', {
            'type': 'error',
            'message': f'A critical background error occurred: {e}'
        })
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
    url = (json_data or {}).get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL is required.'})
        return

    socketio.start_background_task(target=run_scan_in_background, url=url)
    socketio.emit('scan_update', {
        'type': 'status',
        'message': 'Scan request received, process starting in background.'
    })

if __name__ == '__main__':
    # Keep your existing dev run pattern
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
