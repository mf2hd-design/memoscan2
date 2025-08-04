# --- THIS IS THE CRITICAL FIX ---
# Monkey patching must happen at the very beginning of the application lifecycle.
import gevent.monkey
gevent.monkey.patch_all()

import os
import base64
from flask import Flask, request, send_from_directory, send_file, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from io import BytesIO
from dotenv import load_dotenv
from scanner import run_full_scan_stream, SHARED_CACHE

load_dotenv()

app = Flask(__name__, static_folder='.')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

def run_scan_in_background(sid, data):
    """
    This function is designed to be run in a background thread.
    It performs the full scan and emits updates back to the specific client.
    """
    url = data.get("url")
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url}")
    try:
        for update in run_full_scan_stream(url, SHARED_CACHE):
            socketio.emit("scan_update", update, room=sid)
            socketio.sleep(0)
    except Exception as e:
        print(f"ERROR IN BACKGROUND TASK for SID {sid}: {e}")
        socketio.emit("scan_update", {
            "type": "error",
            "message": f"A critical error occurred in the background task: {str(e)}"
        }, room=sid)
    finally:
        print(f"BACKGROUND SCAN FINISHED for SID: {sid}")

@socketio.on('connect')
def handle_connect():
    """
    When a client connects, they are placed in a unique room named after
    their session ID. This allows us to send messages to them directly.
    """
    join_room(request.sid)
    print(f"Client connected and joined room: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """
    When a client disconnects, they are removed from their room.
    """
    leave_room(request.sid)
    print(f"Client disconnected and left room: {request.sid}")

@app.route("/")
def index():
    return send_from_directory('templates', 'index.html')

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route("/screenshot/<screenshot_id>")
def get_screenshot(screenshot_id):
    img_base64 = SHARED_CACHE.get(screenshot_id)
    if not img_base64:
        return jsonify({"error": "Screenshot not found"}), 404
    img_data = base64.b64decode(img_base64)
    return send_file(BytesIO(img_data), mimetype='image/png')

@socketio.on('start_scan')
def handle_start_scan(data):
    """
    This function now only starts the background task and returns immediately.
    """
    url = data.get("url")
    if not url:
        emit("scan_update", {"type": "error", "message": "No URL provided."})
        return

    socketio.start_background_task(run_scan_in_background, request.sid, data)
    print(f"Dispatched scan to background task for SID: {request.sid}")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5050)