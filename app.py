
# --- THIS IS THE CRITICAL FIX ---
# Monkey patching must happen at the very beginning of the application lifecycle.
import gevent.monkey
gevent.monkey.patch_all()

import os
import base64
import time
import uuid
from collections import defaultdict, deque
from flask import Flask, request, send_from_directory, send_file, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from io import BytesIO
from dotenv import load_dotenv
# Import record_feedback from scanner.py
from scanner import run_full_scan_stream, SHARED_CACHE, record_feedback, _validate_url, _clean_url, analyze_feedback_patterns, get_prompt_improvements_from_feedback

load_dotenv()

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 5  # requests per window
RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds
rate_limit_store = defaultdict(deque)

# Request timeout and concurrency protection
REQUEST_TIMEOUT = 600  # 10 minutes maximum per scan
MAX_CONCURRENT_SCANS = 10  # per server instance
active_scans = {}  # {scan_id: start_time}

class RateLimiter:
    last_cleanup = time.time()
    CLEANUP_INTERVAL = 3600  # 1 hour cleanup cycle
    
    @staticmethod
    def _cleanup_old_entries():
        """Periodically clean up old IP entries to prevent memory growth."""
        now = time.time()
        if now - RateLimiter.last_cleanup > RateLimiter.CLEANUP_INTERVAL:
            cutoff_time = now - RATE_LIMIT_WINDOW
            ips_to_remove = []
            
            for ip, requests in rate_limit_store.items():
                # Remove old requests from each IP
                while requests and requests[0] < cutoff_time:
                    requests.popleft()
                # Mark completely empty entries for removal
                if not requests:
                    ips_to_remove.append(ip)
            
            # Clean up empty IP entries
            removed_count = 0
            for ip in ips_to_remove:
                if ip in rate_limit_store:  # Double-check existence
                    del rate_limit_store[ip]
                    removed_count += 1
            
            if removed_count > 0:
                print(f"Rate limiter cleanup: removed {removed_count} inactive IP entries", flush=True)
            
            RateLimiter.last_cleanup = now
    
    @staticmethod
    def is_rate_limited(client_ip: str) -> tuple[bool, str]:
        """Check if client is rate limited.
        
        Returns:
            tuple: (is_limited, message)
        """
        # Perform periodic cleanup to prevent memory leaks
        RateLimiter._cleanup_old_entries()
        
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
# Default to allow Render domain and common localhost ports for development
default_origins = 'https://memoscan2.onrender.com,http://localhost:5000,http://127.0.0.1:5000'
allowed_origins = os.getenv('ALLOWED_ORIGINS', default_origins).split(',')

# Clean up origins (remove empty strings and whitespace)
allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]

if '*' in allowed_origins:
    print("WARNING: CORS allowing all origins. Set ALLOWED_ORIGINS environment variable for production.", flush=True)
else:
    print(f"CORS configured for origins: {', '.join(allowed_origins)}", flush=True)

socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='gevent')

def cleanup_expired_scans():
    """Remove expired scans to prevent resource leaks."""
    now = time.time()
    expired_scans = [scan_id for scan_id, start_time in active_scans.items() 
                     if now - start_time > REQUEST_TIMEOUT]
    
    for scan_id in expired_scans:
        del active_scans[scan_id]
    
    if expired_scans:
        print(f"Cleaned up {len(expired_scans)} expired scans", flush=True)

def run_scan_in_background(sid, data, scan_id=None):
    url = data.get("url")
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url} (scan_id: {scan_id})", flush=True)
    
    try:
        for update in run_full_scan_stream(url, SHARED_CACHE, preferred_lang='en'):
            # Check if scan has been cancelled or expired
            if scan_id and scan_id not in active_scans:
                print(f"Scan {scan_id} was cancelled or expired, stopping", flush=True)
                break
                
            print(f"📡 APP.PY FORWARDING MESSAGE: {update.get('type', 'unknown')} - {update}", flush=True)
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
        # Clean up scan tracking
        if scan_id and scan_id in active_scans:
            del active_scans[scan_id]
        print(f"BACKGROUND SCAN FINISHED for SID: {sid} (scan_id: {scan_id})", flush=True)

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
    # Use production UI with fallbacks
    try:
        return send_from_directory('templates', 'index_production.html')
    except:
        try:
            return send_from_directory('templates', 'index_enhanced.html')
        except:
            return send_from_directory('templates', 'index.html')

@app.route("/screenshot/<screenshot_id>")
def get_screenshot(screenshot_id):
    img_base64 = SHARED_CACHE.get(screenshot_id)
    if not img_base64:
        return jsonify({"error": "Screenshot not found"}), 404
    img_data = base64.b64decode(img_base64)
    return send_file(BytesIO(img_data), mimetype='image/png')

@app.route("/health")
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    cleanup_expired_scans()  # Clean up while we're checking health
    
    return jsonify({
        "status": "healthy",
        "active_scans": len(active_scans),
        "cache_size": len(SHARED_CACHE),
        "rate_limit_ips": len(rate_limit_store),
        "timestamp": time.time(),
        "version": "2.0.0"
    }), 200

def validate_feedback_input(data):
    """Validate and sanitize feedback input to prevent XSS and data issues."""
    import html
    
    errors = []
    
    # Validate required fields
    analysis_id = data.get("analysis_id", "").strip()
    key_name = data.get("key_name", "").strip()
    feedback_type = data.get("feedback_type", "").strip()
    
    if not analysis_id or len(analysis_id) > 100:
        errors.append("Invalid analysis ID")
    if not key_name or key_name not in ["Emotion", "Attention", "Story", "Involvement", "Repetition", "Consistency"]:
        errors.append("Invalid key name")
    if feedback_type not in ["too_high", "about_right", "too_low"]:
        errors.append("Invalid feedback type")
    
    # Validate and sanitize scores
    ai_score = data.get("ai_score")
    user_score = data.get("user_score")
    confidence = data.get("confidence")
    
    if ai_score is not None and not (isinstance(ai_score, int) and 0 <= ai_score <= 5):
        errors.append("AI score must be integer between 0-5")
    if user_score is not None and not (isinstance(user_score, int) and 0 <= user_score <= 5):
        errors.append("User score must be integer between 0-5")
    if confidence is not None and not (isinstance(confidence, int) and 0 <= confidence <= 100):
        errors.append("Confidence must be integer between 0-100")
    
    # Sanitize text inputs
    comment = data.get("comment", "").strip()
    brand_context = data.get("brand_context", "").strip()
    
    if len(comment) > 1000:
        errors.append("Comment too long (max 1000 characters)")
    if len(brand_context) > 200:
        errors.append("Brand context too long (max 200 characters)")
    
    # Sanitize HTML/script content to prevent XSS
    comment = html.escape(comment) if comment else None
    brand_context = html.escape(brand_context) if brand_context else None
    
    return errors, {
        "analysis_id": analysis_id,
        "key_name": key_name,
        "feedback_type": feedback_type,
        "comment": comment,
        "ai_score": ai_score,
        "user_score": user_score,
        "confidence": confidence,
        "brand_context": brand_context
    }

@app.route("/feedback", methods=["POST"])
def handle_feedback():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # Validate and sanitize input
        errors, sanitized_data = validate_feedback_input(data)
        if errors:
            return jsonify({"status": "error", "message": "; ".join(errors)}), 400

        record_feedback(
            sanitized_data["analysis_id"], 
            sanitized_data["key_name"], 
            sanitized_data["feedback_type"], 
            sanitized_data["comment"],
            sanitized_data["ai_score"], 
            sanitized_data["user_score"], 
            sanitized_data["confidence"], 
            sanitized_data["brand_context"]
        )
        return jsonify({"status": "success", "message": "Enhanced feedback recorded"}), 200
    except Exception as e:
        print(f"Error handling feedback: {e}", flush=True)
        return jsonify({"status": "error", "message": "Failed to record feedback"}), 500

@app.route("/feedback/analytics")
def feedback_analytics():
    """Analytics endpoint for monitoring feedback patterns and AI learning."""
    try:
        patterns = analyze_feedback_patterns()
        return jsonify(patterns), 200
    except Exception as e:
        print(f"Error generating feedback analytics: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/feedback/improvements")
def feedback_improvements():
    """Get suggested prompt improvements based on feedback analysis."""
    try:
        improvements = get_prompt_improvements_from_feedback()
        return jsonify(improvements), 200
    except Exception as e:
        print(f"Error generating prompt improvements: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@socketio.on('start_scan')
def handle_start_scan(data):
    # Clean up expired scans first
    cleanup_expired_scans()
    
    # Check concurrent scan limit
    if len(active_scans) >= MAX_CONCURRENT_SCANS:
        emit("scan_update", {"type": "error", "message": "Server is busy. Please try again in a few minutes."})
        print(f"Rejected scan request: {len(active_scans)} concurrent scans already running", flush=True)
        return
    
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

    # Create scan tracking ID and register the scan
    scan_id = str(uuid.uuid4())
    active_scans[scan_id] = time.time()
    
    socketio.start_background_task(run_scan_in_background, request.sid, data, scan_id)
    print(f"Dispatched scan to background task for SID: {request.sid} from IP: {client_ip} (scan_id: {scan_id})", flush=True)
