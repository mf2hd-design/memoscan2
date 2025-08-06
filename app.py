
# --- THIS IS THE CRITICAL FIX ---
# Monkey patching must happen at the very beginning of the application lifecycle.
import gevent.monkey
gevent.monkey.patch_all()

import os
import base64
import time
import uuid
import hashlib
import hmac
import secrets
from functools import wraps
from collections import defaultdict, deque
from flask import Flask, request, send_from_directory, send_file, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from io import BytesIO
from dotenv import load_dotenv
# Import record_feedback from scanner.py
from scanner import run_full_scan_stream, SHARED_CACHE, record_feedback, _validate_url, _clean_url, analyze_feedback_patterns, get_prompt_improvements_from_feedback, get_cost_summary, run_retention_cleanup, get_scan_metrics, track_scan_metric

load_dotenv()

# Admin authentication configuration
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    # Generate a secure default key if not set
    ADMIN_API_KEY = base64.b64encode(os.urandom(32)).decode('utf-8')
    print("WARNING: No ADMIN_API_KEY set. Using generated key. Check logs for key retrieval.", flush=True)
    print("Set ADMIN_API_KEY environment variable for production!", flush=True)
    # Write key to a secure file instead of logging
    try:
        key_file = os.path.join(os.getenv("PERSISTENT_DATA_DIR", "/tmp"), ".admin_key")
        with open(key_file, "w") as f:
            f.write(f"Generated Admin API Key: {ADMIN_API_KEY}\n")
        os.chmod(key_file, 0o600)  # Readable only by owner
        print(f"Generated admin key saved to {key_file} (secure access only)", flush=True)
    except Exception as e:
        print(f"WARNING: Could not save admin key securely: {e}", flush=True)

def require_admin_auth(f):
    """Decorator for admin endpoint authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        # Check Bearer token
        if auth_header and auth_header.startswith('Bearer '):
            provided_key = auth_header[7:]
            if hmac.compare_digest(provided_key, ADMIN_API_KEY):
                return f(*args, **kwargs)
        
        # Check API key in query params (less secure, for convenience)
        provided_key = request.args.get('api_key')
        if provided_key and hmac.compare_digest(provided_key, ADMIN_API_KEY):
            return f(*args, **kwargs)
        
        return jsonify({"error": "Unauthorized. Provide valid API key via Authorization header or api_key parameter."}), 401
    
    return decorated_function

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 5  # requests per window
RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds
rate_limit_store = defaultdict(deque)

# Request timeout and concurrency protection
REQUEST_TIMEOUT = 600  # 10 minutes maximum per scan
MAX_CONCURRENT_SCANS = 10  # per server instance
active_scans = {}  # {scan_id: start_time}

# User session tracking
user_sessions = {}  # {session_id: {'scans': [], 'last_active': timestamp}}
MAX_SCANS_PER_USER = 20  # per 24 hours
USER_SESSION_CLEANUP_INTERVAL = 3600  # 1 hour

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

# Session configuration
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
if not os.getenv('SECRET_KEY'):
    print("WARNING: No SECRET_KEY set. Using generated session key.", flush=True)
    print("Set SECRET_KEY environment variable for production!", flush=True)

# Security configuration
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'memoscan_session'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24  # 24 hours

# CSRF configuration
CSRF_TOKEN_LENGTH = 32

def generate_csrf_token():
    """Generate a new CSRF token."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(CSRF_TOKEN_LENGTH)
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate CSRF token."""
    return token and 'csrf_token' in session and hmac.compare_digest(token, session['csrf_token'])

# Session management functions
def get_user_session_id():
    """Get or create user session ID."""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        session.permanent = True
    return session['user_id']

def track_user_scan(user_id, scan_id, url):
    """Track scan for user session."""
    now = time.time()
    if user_id not in user_sessions:
        user_sessions[user_id] = {'scans': deque(), 'last_active': now}
    
    user_session = user_sessions[user_id]
    user_session['last_active'] = now
    user_session['scans'].append({
        'scan_id': scan_id,
        'url': url,
        'timestamp': now,
        'completed': False
    })
    
    # Keep only last 100 scans per user
    while len(user_session['scans']) > 100:
        user_session['scans'].popleft()

def is_user_rate_limited(user_id):
    """Check if user has exceeded scan limits."""
    if user_id not in user_sessions:
        return False, ""
    
    now = time.time()
    cutoff = now - 86400  # 24 hours
    
    # Count scans in last 24 hours
    recent_scans = [s for s in user_sessions[user_id]['scans'] 
                    if s['timestamp'] > cutoff]
    
    if len(recent_scans) >= MAX_SCANS_PER_USER:
        return True, f"User limit exceeded: {MAX_SCANS_PER_USER} scans per 24 hours"
    
    return False, ""

def cleanup_user_sessions():
    """Remove inactive user sessions."""
    now = time.time()
    cutoff = now - (7 * 86400)  # 7 days
    
    to_remove = []
    for user_id, session_data in user_sessions.items():
        if session_data['last_active'] < cutoff:
            to_remove.append(user_id)
    
    for user_id in to_remove:
        del user_sessions[user_id]
    
    if to_remove:
        print(f"Cleaned up {len(to_remove)} inactive user sessions", flush=True)

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Enable XSS protection (though modern browsers have this by default)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Strict transport security (HTTPS only)
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Permissions policy (replace deprecated Feature-Policy)
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    return response

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

def run_scan_in_background(sid, data, scan_id=None, user_id=None):
    url = data.get("url")
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url} (scan_id: {scan_id}, user: {user_id})", flush=True)
    
    try:
        for update in run_full_scan_stream(url, SHARED_CACHE, preferred_lang='en', scan_id=scan_id):
            # Check if scan has been cancelled or expired
            if scan_id and scan_id not in active_scans:
                print(f"Scan {scan_id} was cancelled or expired, stopping", flush=True)
                track_scan_metric(scan_id, "cancelled", {"reason": "user_cancelled"})
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
        
        # Mark scan as completed for user
        if user_id and user_id in user_sessions:
            for scan in user_sessions[user_id]['scans']:
                if scan['scan_id'] == scan_id:
                    scan['completed'] = True
                    break
        
        print(f"BACKGROUND SCAN FINISHED for SID: {sid} (scan_id: {scan_id}, user: {user_id})", flush=True)

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
    # Generate CSRF token for the session
    generate_csrf_token()
    # Use production UI with fallbacks
    try:
        return send_from_directory('templates', 'index_production.html')
    except:
        try:
            return send_from_directory('templates', 'index_enhanced.html')
        except:
            return send_from_directory('templates', 'index.html')

@app.route("/csrf-token")
def get_csrf_token():
    """Get CSRF token for API requests."""
    token = generate_csrf_token()
    return jsonify({"csrf_token": token}), 200

@app.route("/user/history")
def user_history():
    """Get scan history for current user session."""
    user_id = get_user_session_id()
    
    if user_id not in user_sessions:
        return jsonify({"scans": [], "total": 0}), 200
    
    # Get recent scans
    scans = list(user_sessions[user_id]['scans'])
    scans.reverse()  # Most recent first
    
    # Calculate stats
    now = time.time()
    last_24h = [s for s in scans if s['timestamp'] > now - 86400]
    
    return jsonify({
        "user_id": user_id,
        "scans": scans[:50],  # Last 50 scans
        "total": len(scans),
        "last_24h": len(last_24h),
        "remaining_24h": max(0, MAX_SCANS_PER_USER - len(last_24h))
    }), 200

@app.route("/screenshot/<screenshot_id>")
def get_screenshot(screenshot_id):
    img_base64 = SHARED_CACHE.get(screenshot_id)
    if not img_base64:
        return jsonify({"error": "Screenshot not found"}), 404
    img_data = base64.b64decode(img_base64)
    return send_file(BytesIO(img_data), mimetype='image/png')

def get_system_resources():
    """Get system resource usage."""
    import psutil
    try:
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage for persistent data directory
        data_dir = os.getenv("PERSISTENT_DATA_DIR", "/data")
        disk_usage = psutil.disk_usage(data_dir if os.path.exists(data_dir) else "/")
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        return {
            "memory": {
                "total_mb": round(memory.total / (1024**2)),
                "available_mb": round(memory.available / (1024**2)),
                "percent_used": memory.percent,
                "status": "critical" if memory.percent > 90 else "warning" if memory.percent > 80 else "healthy"
            },
            "disk": {
                "total_gb": round(disk_usage.total / (1024**3)),
                "free_gb": round(disk_usage.free / (1024**3)),
                "percent_used": round((disk_usage.used / disk_usage.total) * 100, 1),
                "status": "critical" if (disk_usage.used / disk_usage.total) > 0.9 else "warning" if (disk_usage.used / disk_usage.total) > 0.8 else "healthy"
            },
            "cpu": {
                "percent_used": cpu_percent,
                "status": "critical" if cpu_percent > 90 else "warning" if cpu_percent > 80 else "healthy"
            }
        }
    except ImportError:
        return {"error": "psutil not available for system monitoring"}
    except Exception as e:
        return {"error": f"Failed to get system resources: {e}"}

@app.route("/health")
def health_check():
    """Health check endpoint for monitoring and load balancers."""
    cleanup_expired_scans()  # Clean up while we're checking health
    
    # Get cache stats if available
    cache_stats = SHARED_CACHE.get_stats() if hasattr(SHARED_CACHE, 'get_stats') else {"items": len(SHARED_CACHE)}
    
    # Get system resources
    system_resources = get_system_resources()
    
    # Determine overall health
    health_status = "healthy"
    if isinstance(system_resources, dict) and "error" not in system_resources:
        resource_statuses = [
            system_resources.get("memory", {}).get("status", "unknown"),
            system_resources.get("disk", {}).get("status", "unknown"),
            system_resources.get("cpu", {}).get("status", "unknown")
        ]
        if "critical" in resource_statuses:
            health_status = "critical"
        elif "warning" in resource_statuses:
            health_status = "warning"
    
    response = {
        "status": health_status,
        "active_scans": len(active_scans),
        "cache": cache_stats,
        "rate_limit_ips": len(rate_limit_store),
        "system": system_resources,
        "timestamp": time.time(),
        "version": "2.0.0"
    }
    
    # Return appropriate HTTP status
    status_code = 503 if health_status == "critical" else 200
    return jsonify(response), status_code

def validate_feedback_input(data):
    """Validate and sanitize feedback input to prevent XSS and data issues."""
    
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
    
    # Enhanced sanitization to prevent XSS
    def sanitize_text(text):
        if not text:
            return None
        
        try:
            # Try to use bleach for robust sanitization
            import bleach
            # Allow only safe tags and attributes
            allowed_tags = []  # No HTML tags allowed in feedback
            allowed_attributes = {}
            return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)
        except ImportError:
            # Fallback to basic HTML escaping
            import html
            # Remove potential script content and escape HTML
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
            text = re.sub(r'on\w+\s*=', '', text, flags=re.IGNORECASE)  # Remove event handlers
            return html.escape(text)
    
    comment = sanitize_text(comment)
    brand_context = sanitize_text(brand_context)
    
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
        
        # Validate CSRF token
        csrf_token = request.headers.get('X-CSRF-Token') or data.get('csrf_token')
        if not validate_csrf_token(csrf_token):
            return jsonify({"status": "error", "message": "Invalid or missing CSRF token"}), 403
        
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
@require_admin_auth
def feedback_analytics():
    """Analytics endpoint for monitoring feedback patterns and AI learning."""
    try:
        patterns = analyze_feedback_patterns()
        return jsonify(patterns), 200
    except Exception as e:
        print(f"Error generating feedback analytics: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/feedback/improvements")
@require_admin_auth
def feedback_improvements():
    """Get suggested prompt improvements based on feedback analysis."""
    try:
        improvements = get_prompt_improvements_from_feedback()
        return jsonify(improvements), 200
    except Exception as e:
        print(f"Error generating prompt improvements: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/costs")
@require_admin_auth
def api_costs():
    """Get API usage costs summary."""
    hours = request.args.get('hours', 24, type=int)
    try:
        costs = get_cost_summary(hours)
        return jsonify(costs), 200
    except Exception as e:
        print(f"Error generating cost summary: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/admin/retention-cleanup", methods=["POST"])
@require_admin_auth
def trigger_retention_cleanup():
    """Manually trigger data retention cleanup."""
    try:
        run_retention_cleanup()
        return jsonify({"status": "success", "message": "Retention cleanup completed"}), 200
    except Exception as e:
        print(f"Error running retention cleanup: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/metrics")
@require_admin_auth
def scan_metrics():
    """Get scan metrics and completion rates."""
    hours = request.args.get('hours', 24, type=int)
    try:
        metrics = get_scan_metrics(hours)
        return jsonify(metrics), 200
    except Exception as e:
        print(f"Error generating metrics: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@socketio.on('start_scan')
def handle_start_scan(data):
    # Clean up expired scans and sessions
    cleanup_expired_scans()
    cleanup_user_sessions()
    
    # Get user session
    user_id = get_user_session_id()
    
    # Check user-specific rate limit
    user_limited, user_limit_msg = is_user_rate_limited(user_id)
    if user_limited:
        emit("scan_update", {"type": "error", "message": user_limit_msg})
        print(f"User rate limited {user_id}: {user_limit_msg}", flush=True)
        return
    
    # Check concurrent scan limit
    if len(active_scans) >= MAX_CONCURRENT_SCANS:
        emit("scan_update", {"type": "error", "message": "Server is busy. Please try again in a few minutes."})
        print(f"Rejected scan request: {len(active_scans)} concurrent scans already running", flush=True)
        return
    
    # Get client IP for rate limiting
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    
    # Check IP-based rate limiting
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
    
    # Track scan for user
    track_user_scan(user_id, scan_id, cleaned_url)
    
    socketio.start_background_task(run_scan_in_background, request.sid, data, scan_id, user_id)
    print(f"Dispatched scan to background task for SID: {request.sid} from IP: {client_ip}, user: {user_id} (scan_id: {scan_id})", flush=True)

# Graceful shutdown handling
import signal
import sys

shutting_down = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutting_down
    shutting_down = True
    
    print(f"\nReceived signal {signum}, initiating graceful shutdown...", flush=True)
    
    # Cancel all active scans
    for scan_id in list(active_scans.keys()):
        print(f"Cancelling scan {scan_id}", flush=True)
        del active_scans[scan_id]
    
    # Give time for background tasks to notice cancellation
    time.sleep(2)
    
    # Log final stats
    if hasattr(SHARED_CACHE, 'get_stats'):
        print(f"Final cache stats: {SHARED_CACHE.get_stats()}", flush=True)
    
    print("Graceful shutdown complete.", flush=True)
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Add endpoint to check if server is shutting down
@app.route("/status")
def server_status():
    """Check server status including shutdown state."""
    return jsonify({
        "shutting_down": shutting_down,
        "active_scans": len(active_scans),
        "accepting_requests": not shutting_down and len(active_scans) < MAX_CONCURRENT_SCANS
    }), 200

@app.route("/health/dependencies")
@require_admin_auth
def health_check_dependencies():
    """Deep health check for external dependencies."""
    import httpx
    from openai import OpenAI
    
    dependencies = {
        "openai": {"status": "unknown", "latency_ms": None},
        "scrapfly": {"status": "unknown", "latency_ms": None},
        "storage": {"status": "unknown", "writable": False},
        "playwright": {"status": "unknown"}
    }
    
    # Check OpenAI API
    try:
        start = time.time()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # Use a minimal test to check connectivity
        response = client.models.list()
        latency = (time.time() - start) * 1000
        dependencies["openai"] = {
            "status": "healthy", 
            "latency_ms": round(latency, 2),
            "models_available": len(list(response))
        }
    except Exception as e:
        dependencies["openai"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Scrapfly API (if configured)
    scrapfly_key = os.getenv("SCRAPFLY_KEY")
    if scrapfly_key:
        try:
            start = time.time()
            response = httpx.get(
                "https://api.scrapfly.io/account",
                headers={"x-api-key": scrapfly_key},
                timeout=5
            )
            latency = (time.time() - start) * 1000
            if response.status_code == 200:
                dependencies["scrapfly"] = {
                    "status": "healthy",
                    "latency_ms": round(latency, 2)
                }
            else:
                dependencies["scrapfly"] = {
                    "status": "unhealthy",
                    "status_code": response.status_code
                }
        except Exception as e:
            dependencies["scrapfly"] = {"status": "unhealthy", "error": str(e)}
    else:
        dependencies["scrapfly"] = {"status": "not_configured"}
    
    # Check storage writability
    try:
        test_file = os.path.join(os.getenv("PERSISTENT_DATA_DIR", "/data"), ".health_check")
        with open(test_file, "w") as f:
            f.write(str(time.time()))
        os.unlink(test_file)
        dependencies["storage"] = {"status": "healthy", "writable": True}
    except Exception as e:
        dependencies["storage"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Playwright availability
    try:
        from playwright.sync_api import sync_playwright
        dependencies["playwright"] = {"status": "healthy", "available": True}
    except Exception as e:
        dependencies["playwright"] = {"status": "unhealthy", "error": str(e)}
    
    # Overall health status
    all_healthy = all(
        dep.get("status") in ["healthy", "not_configured"] 
        for dep in dependencies.values()
    )
    
    return jsonify({
        "overall_status": "healthy" if all_healthy else "degraded",
        "dependencies": dependencies,
        "timestamp": time.time()
    }), 200 if all_healthy else 503
