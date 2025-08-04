
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
# Import record_feedback from scanner.py
from scanner import run_full_scan_stream, SHARED_CACHE, record_feedback

load_dotenv()

# IMPORTANT: Specify static_folder and template_folder explicitly
app = Flask(__name__, static_folder='static', template_folder='templates')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

def run_scan_in_background(sid, data):
    url = data.get("url")
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url}", flush=True)
    try:
        for update in run_full_scan_stream(url, SHARED_CACHE):
            socketio.emit("scan_update", update, room=sid)
            socketio.sleep(0)
    except Exception as e:
        print(f"ERROR IN BACKGROUND TASK for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": f"A critical error occurred in the background task: {str(e)}"
        }, room=sid)
    finally:
        print(f"BACKGROUND SCAN FINISHED for SID: {sid}", flush=True)

@socketio.on('connect')
def handle_connect():
    join_room(request.sid)
    print(f"Client connected and joined room: {request.sid}", flush=True)

@socketio.on('disconnect')
def handle_disconnect():
    leave_room(request.sid)
    print(f"Client disconnected and left room: {request.sid}", flush=True)

@app.route("/")
def index():
    return send_from_directory('templates', 'index.html')

@app.route("/screenshot/<screenshot_id>")
def get_screenshot(screenshot_id):
    img_base64 = SHARED_CACHE.get(screenshot_id)
    if not img_base64:
        return jsonify({"error": "Screenshot not found"}), 404
    img_data = base64.b64decode(img_base64)
    return send_file(BytesIO(img_data), mimetype='image/png')

@app.route("/feedback", methods=["POST"])
def handle_feedback():
    try:
        data = request.get_json()
        analysis_id = data.get("analysis_id")
        key_name = data.get("key_name")
        feedback_type = data.get("feedback_type")
        comment = data.get("comment")

        if not all([analysis_id, key_name, feedback_type]):
            return jsonify({"status": "error", "message": "Missing required feedback data"}), 400

        record_feedback(analysis_id, key_name, feedback_type, comment)
        return jsonify({"status": "success", "message": "Feedback recorded"}), 200
    except Exception as e:
        print(f"Error handling feedback: {e}", flush=True)
        return jsonify({"status": "error", "message": f"Failed to record feedback: {str(e)}"}), 500

@socketio.on('start_scan')
def handle_start_scan(data):
    url = data.get("url")
    if not url:
        emit("scan_update", {"type": "error", "message": "No URL provided."})
        return

    socketio.start_background_task(run_scan_in_background, request.sid, data)
    print(f"Dispatched scan to background task for SID: {request.sid}", flush=True)
