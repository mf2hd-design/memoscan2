
# --- THIS IS THE CRITICAL FIX ---
# Monkey patching must happen at the very beginning of the application lifecycle.
import gevent.monkey
gevent.monkey.patch_all()

import os
import base64
import time
from collections import defaultdict, deque
from flask import Flask, request, send_from_directory, send_file, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from io import BytesIO
from dotenv import load_dotenv
# Import record_feedback from scanner.py
from scanner import run_full_scan_stream, SHARED_CACHE, record_feedback, _validate_url, _clean_url

load_dotenv()

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 5  # requests per window
RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds
rate_limit_store = defaultdict(deque)

class RateLimiter:
    @staticmethod
    def is_rate_limited(client_ip: str) -> tuple[bool, str]:
        """Check if client is rate limited.
        
        Returns:
            tuple: (is_limited, message)
        """
        now = time.time()
        client_requests = rate_limit_store[client_ip]
        
        # Remove old requests outside the window
        while client_requests and client_requests[0] < now - RATE_LIMIT_WINDOW:
            client_requests.popleft()
        
        # Check if limit exceeded
        if len(client_requests) >= RATE_LIMIT_REQUESTS:
            remaining_time = int(RATE_LIMIT_WINDOW - (now - client_requests[0]))
            return True, f"Rate limit exceeded. Try again in {remaining_time} seconds."
        
        # Add current request
        client_requests.append(now)
        return False, ""

# IMPORTANT: Specify static_folder and template_folder explicitly
app = Flask(__name__, static_folder='static', template_folder='templates')

# CORS configuration - restrict origins in production
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
if allowed_origins == ['*']:
    print("WARNING: CORS allowing all origins. Set ALLOWED_ORIGINS environment variable for production.", flush=True)

socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='gevent')

def run_scan_in_background(sid, data):
    url = data.get("url")
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url}", flush=True)
    try:
        for update in run_full_scan_stream(url, SHARED_CACHE):
            socketio.emit("scan_update", update, room=sid)
            socketio.sleep(0)
    except ValueError as e:
        # Input validation errors
        print(f"VALIDATION ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": f"Invalid input: {str(e)}"
        }, room=sid)
    except ConnectionError as e:
        # Network/connection errors
        print(f"CONNECTION ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": "Unable to connect to the target website. Please check the URL and try again."
        }, room=sid)
    except TimeoutError as e:
        # Timeout errors
        print(f"TIMEOUT ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": "The scan timed out. The website may be slow or unavailable."
        }, room=sid)
    except Exception as e:
        # Unexpected errors
        print(f"UNEXPECTED ERROR for SID {sid}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        socketio.emit("scan_update", {
            "type": "error",
            "message": "An unexpected error occurred. Please try again later."
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
    # Get client IP for rate limiting
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    
    # Check rate limiting
    is_limited, limit_msg = RateLimiter.is_rate_limited(client_ip)
    if is_limited:
        emit("scan_update", {"type": "error", "message": limit_msg})
        print(f"Rate limited request from {client_ip}: {limit_msg}", flush=True)
        return
    
    url = data.get("url")
    if not url:
        emit("scan_update", {"type": "error", "message": "No URL provided."})
        return
    
    # Validate URL before processing
    cleaned_url = _clean_url(url)
    is_valid, error_msg = _validate_url(cleaned_url)
    if not is_valid:
        emit("scan_update", {"type": "error", "message": f"Invalid URL: {error_msg}"})
        print(f"URL validation failed for {url}: {error_msg}", flush=True)
        return

    socketio.start_background_task(run_scan_in_background, request.sid, data)
    print(f"Dispatched scan to background task for SID: {request.sid} from IP: {client_ip}", flush=True)
