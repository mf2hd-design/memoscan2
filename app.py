
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
import json
from flask_socketio import SocketIO, emit, join_room, leave_room
from io import BytesIO
import signal
from threading import Event
from dotenv import load_dotenv
# Import record_feedback from scanner.py
from scanner import SHARED_CACHE, record_feedback, _validate_url, _clean_url, analyze_feedback_patterns, get_prompt_improvements_from_feedback, get_cost_summary, run_retention_cleanup, get_scan_metrics, track_scan_metric, start_background_threads

# Discovery Mode imports
try:
    from discovery_integration import DiscoveryFeedbackHandler, FeatureFlags
    from discovery_schemas import DiscoveryFeedback
    DISCOVERY_MODE_AVAILABLE = True
    # Use the Discovery-optimized scanner for Discovery Mode
    from scanner_discovery import run_full_scan_stream as run_discovery_scan_stream, init_discovery_mode
    
    # Initialize Discovery Mode when components are available
    discovery_init_result = init_discovery_mode()
    if discovery_init_result:
        print("✅ Discovery Mode with concurrent API optimization initialized successfully", flush=True)
    else:
        print("⚠️ Discovery Mode components loaded but initialization failed (check OPENAI_API_KEY)", flush=True)
        DISCOVERY_MODE_AVAILABLE = False
except ImportError:
    DISCOVERY_MODE_AVAILABLE = False
    print("Discovery Mode components not available", flush=True)

# Import regular scanner for diagnosis mode
from scanner import run_full_scan_stream as run_diagnosis_scan_stream

load_dotenv()

# Ensure PERSISTENT_DATA_DIR is set for Discovery Mode
if not os.getenv("PERSISTENT_DATA_DIR"):
    # Use a writable directory for local development
    local_data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(local_data_dir, exist_ok=True)
    os.environ["PERSISTENT_DATA_DIR"] = local_data_dir
    print(f"✅ Set PERSISTENT_DATA_DIR to: {local_data_dir}", flush=True)

# Admin authentication configuration
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    # Generate secure key but don't log it
    import secrets
    ADMIN_API_KEY = secrets.token_urlsafe(32)
    
    # Store in secure location accessible only to admin
    secure_dir = os.getenv("SECURE_CONFIG_DIR", os.path.join(os.getenv("PERSISTENT_DATA_DIR", "/tmp"), "secure"))
    key_file = os.path.join(secure_dir, "admin.key")
    
    try:
        os.makedirs(secure_dir, mode=0o700, exist_ok=True)
        with open(key_file, "w") as f:
            f.write(ADMIN_API_KEY)
        os.chmod(key_file, 0o600)  # Owner read/write only
        print(f"SECURITY: Admin key generated and stored securely at {key_file}")
        print("Set ADMIN_API_KEY environment variable for production!")
    except Exception as e:
        print("ERROR: Could not store admin key securely. This is a security risk.")
        print(f"Error: {e}")
        print("Consider setting ADMIN_API_KEY environment variable manually.")

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
default_origins = 'https://memoscan2.onrender.com,http://localhost:5000,http://127.0.0.1:5000,http://localhost:8081,http://127.0.0.1:8081'
allowed_origins = os.getenv('ALLOWED_ORIGINS', default_origins).split(',')

# Clean up origins (remove empty strings and whitespace)
allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]

if '*' in allowed_origins:
    print("WARNING: CORS allowing all origins. Set ALLOWED_ORIGINS environment variable for production.", flush=True)
else:
    print(f"CORS configured for origins: {', '.join(allowed_origins)}", flush=True)

socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='gevent')

# Start background threads after app initialization
start_background_threads()

# Graceful shutdown handling
shutdown_event = Event()

def _graceful_shutdown(*_args):
    print("Received shutdown signal, draining...", flush=True)
    shutdown_event.set()
    try:
        from scanner import close_shared_http_client, close_shared_playwright_browser
        close_shared_http_client()
        close_shared_playwright_browser()
    except Exception as e:
        print(f"Shutdown cleanup failed: {e}", flush=True)

signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)

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
    mode = data.get("mode", "diagnosis")  # Extract mode from data
    print(f"BACKGROUND SCAN STARTED for SID: {sid} on URL: {url} (scan_id: {scan_id}, user: {user_id}, mode: {mode})", flush=True)
    
    try:
        # Use the appropriate scanner based on mode
        if mode == "discovery" and DISCOVERY_MODE_AVAILABLE:
            scan_stream = run_discovery_scan_stream(url, SHARED_CACHE, preferred_lang='en', scan_id=scan_id, mode=mode)
        else:
            # Diagnosis stream does not accept a 'mode' argument
            scan_stream = run_diagnosis_scan_stream(url, SHARED_CACHE, preferred_lang='en', scan_id=scan_id)
        # Track scan start for dashboard visibility (all modes)
        try:
            track_scan_metric(scan_id, "started", {"mode": mode, "url": url})
        except Exception:
            pass

        for update in scan_stream:
            # Check if scan has been cancelled or expired
            if scan_id and scan_id not in active_scans:
                print(f"Scan {scan_id} was cancelled or expired, stopping", flush=True)
                track_scan_metric(scan_id, "cancelled", {"reason": "user_cancelled"})
                break
                
            print(f"📡 APP.PY FORWARDING MESSAGE: {update.get('type', 'unknown')} - {update}", flush=True)
            socketio.emit("scan_update", update, room=sid)
            socketio.sleep(0)

            # Track completion/failure for dashboard (all modes)
            try:
                if update.get("type") == "complete":
                    track_scan_metric(scan_id, "completed", {"mode": mode})
                elif update.get("type") == "error":
                    track_scan_metric(scan_id, "failed", {"mode": mode, "error": update.get("message")})
            except Exception:
                pass
    except ValueError as e:
        # Input validation errors
        print(f"VALIDATION ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": f"Invalid input: {str(e)}"
        }, room=sid)
        try:
            track_scan_metric(scan_id, "failed", {"mode": mode, "error": str(e)})
        except Exception:
            pass
    except ConnectionError as e:
        # Network/connection errors
        print(f"CONNECTION ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": "Unable to connect to the target website. Please check the URL and try again."
        }, room=sid)
        try:
            track_scan_metric(scan_id, "failed", {"mode": mode, "error": str(e)})
        except Exception:
            pass
    except TimeoutError as e:
        # Timeout errors
        print(f"TIMEOUT ERROR for SID {sid}: {e}", flush=True)
        socketio.emit("scan_update", {
            "type": "error",
            "message": "The scan timed out. The website may be slow or unavailable."
        }, room=sid)
        try:
            track_scan_metric(scan_id, "failed", {"mode": mode, "error": str(e)})
        except Exception:
            pass
    except Exception as e:
        # Unexpected errors
        print(f"UNEXPECTED ERROR for SID {sid}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        socketio.emit("scan_update", {
            "type": "error",
            "message": "An unexpected error occurred. Please try again later."
        }, room=sid)
        try:
            if mode == "discovery":
                track_scan_metric(scan_id, "failed", {"mode": mode, "error": str(e)})
        except Exception:
            pass
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
    cached_screenshot = SHARED_CACHE.get(screenshot_id)
    if not cached_screenshot:
        return jsonify({"error": "Screenshot not found"}), 404
    
    # New path-first format
    if isinstance(cached_screenshot, dict) and cached_screenshot.get('path'):
        path = cached_screenshot['path']
        # Try to infer mimetype from stored format
        mimetype = cached_screenshot.get('format', 'image/jpeg')
        try:
            return send_file(path, mimetype=mimetype)
        except Exception:
            return jsonify({"error": "Screenshot file not found"}), 404
    
    # Old formats: (dict with base64) or plain base64 string
    if isinstance(cached_screenshot, dict):
        img_base64 = cached_screenshot.get('data')
        mimetype = cached_screenshot.get('format', 'image/png')
    else:
        img_base64 = cached_screenshot
        mimetype = 'image/png'
    if not img_base64:
        return jsonify({"error": "Screenshot data not found"}), 404
    img_data = base64.b64decode(img_base64)
    return send_file(BytesIO(img_data), mimetype=mimetype)

@app.route("/metrics")
def metrics():
    try:
        cache_items = len(SHARED_CACHE)
        return jsonify({
            "active_scans": len(active_scans),
            "cache_items": cache_items,
            "timestamp": time.time()
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Public, user-friendly Dashboard routes (no admin key required) ---
@app.route("/dashboard")
@app.route("/dashboard/<path:subpage>")
def dashboard(subpage=None):
    """Serve the dashboard SPA which renders Metrics, Costs, and Feedback views."""
    try:
        return send_from_directory('templates', 'dashboard.html')
    except Exception as e:
        return jsonify({"error": f"Dashboard not available: {e}"}), 500

@app.route("/dashboard/api/metrics")
def dashboard_metrics_api():
    """Unprotected metrics API for the dashboard UI."""
    hours = request.args.get('hours', 24, type=int)
    try:
        data = get_scan_metrics(hours)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/costs")
def dashboard_costs_api():
    """Unprotected costs API for the dashboard UI."""
    hours = request.args.get('hours', 24, type=int)
    try:
        data = get_cost_summary(hours)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/feedback/analytics")
def dashboard_feedback_analytics_api():
    """Unprotected feedback analytics for the dashboard UI."""
    try:
        data = analyze_feedback_patterns()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/feedback/improvements")
def dashboard_feedback_improvements_api():
    """Unprotected feedback improvements for the dashboard UI."""
    try:
        data = get_prompt_improvements_from_feedback()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/discovery/feedback")
def dashboard_discovery_feedback_api():
    """Unprotected Discovery feedback analytics for the dashboard UI."""
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff = time.time() - (hours * 3600)
        data_dir = os.getenv("PERSISTENT_DATA_DIR", "/data")
        path = os.path.join(data_dir, "discovery_feedback.jsonl")
        summary = {
            "total": 0,
            "helpful_true": 0,
            "helpful_false": 0,
            "by_key": {},
            "by_category": {},
            "recent": []
        }
        entries = []
        if os.path.exists(path):
            try:
                from datetime import datetime as _dt
                with open(path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                        except Exception:
                            continue
                        ts_raw = entry.get("timestamp")
                        # Parse datetime strings of form 'YYYY-MM-DD HH:MM:SS' or ISO
                        ts = None
                        if isinstance(ts_raw, (int, float)):
                            ts = float(ts_raw)
                        elif isinstance(ts_raw, str):
                            try:
                                ts = _dt.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
                            except Exception:
                                ts = None
                        if ts is None or ts < cutoff:
                            continue
                        entries.append((ts, entry))
            except Exception:
                pass

        # Sort by timestamp desc
        entries.sort(key=lambda x: x[0], reverse=True)
        for ts, e in entries:
            summary["total"] += 1
            helpful = bool(e.get("helpful"))
            if helpful:
                summary["helpful_true"] += 1
            else:
                summary["helpful_false"] += 1
            key = e.get("key_name") or "unknown"
            bk = summary["by_key"].setdefault(key, {"count": 0, "helpful": 0})
            bk["count"] += 1
            bk["helpful"] += 1 if helpful else 0
            cat = e.get("category") or "uncategorized"
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            # Recent list
            if len(summary["recent"]) < 50:
                summary["recent"].append({
                    "timestamp": ts,
                    "scan_id": e.get("scan_id"),
                    "key_name": key,
                    "helpful": helpful,
                    "category": e.get("category"),
                    "comment": (e.get("comment") or "")[:200]
                })
        # Compute helpful rate per key
        for key, v in summary["by_key"].items():
            cnt = v.get("count", 0) or 1
            v["helpful_rate"] = v.get("helpful", 0) / cnt
        # Overall helpful rate
        total = summary["total"] or 1
        summary["helpful_rate"] = summary["helpful_true"] / total
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/errors")
def dashboard_errors_api():
    """Combined error feed from diagnosis and discovery."""
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff = time.time() - (hours * 3600)
        data_dir = os.getenv("PERSISTENT_DATA_DIR", "/data")
        results = []

        # Diagnosis failures from scan_metrics.jsonl
        metrics_path = os.path.join(data_dir, "scan_metrics.jsonl")
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        ts = entry.get("timestamp")
                        if isinstance(ts, (int, float)) and ts >= cutoff and entry.get("event_type") == "failed":
                            results.append({
                                "timestamp": ts,
                                "source": "diagnosis",
                                "scan_id": entry.get("scan_id"),
                                "message": (entry.get("details") or {}).get("error") or (entry.get("details") or {}).get("reason") or "failed",
                                "details": entry.get("details")
                            })
            except Exception:
                pass

        # Discovery errors from discovery_errors.jsonl (ISO timestamps)
        d_errors_path = os.path.join(data_dir, "discovery_errors.jsonl")
        if os.path.exists(d_errors_path):
            try:
                from datetime import datetime as _dt
                with open(d_errors_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        iso = entry.get("timestamp")
                        try:
                            ts = _dt.fromisoformat(iso).timestamp() if isinstance(iso, str) else None
                        except Exception:
                            ts = None
                        if ts and ts >= cutoff:
                            results.append({
                                "timestamp": ts,
                                "source": "discovery",
                                "scan_id": entry.get("scan_id"),
                                "key_name": entry.get("key_name"),
                                "message": entry.get("error"),
                                "details": entry
                            })
            except Exception:
                pass

        # Sort newest first
        results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return jsonify({"errors": results[:200]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/metrics/advanced")
def dashboard_metrics_advanced_api():
    """Enhanced metrics including mode and model breakdowns."""
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff = time.time() - (hours * 3600)
        base = get_scan_metrics(hours)

        data_dir = os.getenv("PERSISTENT_DATA_DIR", "/data")
        # Discovery: counts by scan_id from discovery_metrics.jsonl
        discovery_totals = {"total_scans": 0, "completed": 0}
        discovery_scan_ids = set()
        d_metrics_path = os.path.join(data_dir, "discovery_metrics.jsonl")
        if os.path.exists(d_metrics_path):
            try:
                from datetime import datetime as _dt
                with open(d_metrics_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        iso = entry.get("timestamp")
                        try:
                            ts = _dt.fromisoformat(iso).timestamp() if isinstance(iso, str) else None
                        except Exception:
                            ts = None
                        if ts and ts >= cutoff:
                            sid = entry.get("scan_id")
                            if sid and sid not in discovery_scan_ids:
                                discovery_scan_ids.add(sid)
            except Exception:
                pass
        discovery_totals["total_scans"] = len(discovery_scan_ids)
        discovery_totals["completed"] = len(discovery_scan_ids)  # entries are written at end of scan

        # Model breakdowns
        model_counts = {"discovery_analysis_success": {}, "api_calls_by_type": {}}
        # Discovery per-model from discovery_analysis.jsonl where validation_status == "success"
        d_analysis_path = os.path.join(data_dir, "discovery_analysis.jsonl")
        if os.path.exists(d_analysis_path):
            try:
                from datetime import datetime as _dt
                with open(d_analysis_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        iso = entry.get("timestamp")
                        try:
                            ts = _dt.fromisoformat(iso).timestamp() if isinstance(iso, str) else None
                        except Exception:
                            ts = None
                        if not ts or ts < cutoff:
                            continue
                        if (entry.get("validation_status") == "success"):
                            model = entry.get("model_id") or "unknown"
                            model_counts["discovery_analysis_success"][model] = model_counts["discovery_analysis_success"].get(model, 0) + 1
            except Exception:
                pass

        # API calls by type from api_costs.jsonl (includes e.g. gpt-4o)
        costs_path = os.path.join(data_dir, "api_costs.jsonl")
        if os.path.exists(costs_path):
            try:
                with open(costs_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        ts = entry.get("timestamp")
                        if isinstance(ts, (int, float)) and ts >= cutoff:
                            api_type = (entry.get("details") or {}).get("api_type") or entry.get("api_type") or "unknown"
                            model_counts["api_calls_by_type"][api_type] = model_counts["api_calls_by_type"].get(api_type, 0) + 1
            except Exception:
                pass

        # Compose response
        response = {
            "summary": base,
            "by_mode": {
                "diagnosis": base.get("total_scans", 0),
                "discovery": discovery_totals
            },
            "models": model_counts
        }
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/dashboard/api/scans")
def dashboard_scans_api():
    """List recent scans in descending order with start time, duration, status, mode, and errors."""
    try:
        hours = request.args.get('hours', 24, type=int)
        cutoff = time.time() - (hours * 3600)
        data_dir = os.getenv("PERSISTENT_DATA_DIR", "/data")
        metrics_path = os.path.join(data_dir, "scan_metrics.jsonl")
        scans = {}

        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        ts = entry.get("timestamp")
                        if not isinstance(ts, (int, float)) or ts < cutoff:
                            continue
                        sid = entry.get("scan_id")
                        if not sid:
                            continue
                        evt = entry.get("event_type")
                        details = entry.get("details") or {}
                        rec = scans.setdefault(sid, {
                            "scan_id": sid,
                            "start_ts": None,
                            "end_ts": None,
                            "status": "unknown",
                            "mode": details.get("mode") or "diagnosis",
                            "url": details.get("url") or details.get("cleaned_url"),
                            "error": None,
                            "duration_s": None,
                            "discovery_key_errors": []
                        })
                        # Prefer explicit mode if ever provided later
                        if details.get("mode"):
                            rec["mode"] = details.get("mode")
                        if evt == "started":
                            rec["start_ts"] = ts
                            rec["status"] = "started"
                        elif evt == "completed":
                            rec["end_ts"] = ts
                            rec["status"] = "completed"
                        elif evt == "failed":
                            rec["end_ts"] = rec["end_ts"] or ts
                            rec["status"] = "failed"
                            rec["error"] = details.get("error") or details.get("reason")
                        elif evt == "cancelled":
                            rec["end_ts"] = ts
                            rec["status"] = "cancelled"
                        # compute duration when possible
                        if rec["start_ts"] and rec["end_ts"] and rec["duration_s"] is None:
                            rec["duration_s"] = max(0, int(rec["end_ts"] - rec["start_ts"]))
            except Exception:
                pass

        # Merge discovery per-key errors to show where analysis failed
        try:
            d_errors_path = os.path.join(data_dir, "discovery_errors.jsonl")
            if os.path.exists(d_errors_path):
                from datetime import datetime as _dt
                with open(d_errors_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        iso = entry.get("timestamp")
                        try:
                            ts = _dt.fromisoformat(iso).timestamp() if isinstance(iso, str) else None
                        except Exception:
                            ts = None
                        if not ts or ts < cutoff:
                            continue
                        sid = entry.get("scan_id")
                        if sid in scans:
                            key_name = entry.get("key_name") or "unknown"
                            msg = entry.get("error") or (entry.get("metrics") or {}).get("error_details")
                            scans[sid].setdefault("discovery_key_errors", []).append({"key": key_name, "message": msg})
        except Exception:
            pass

        # Merge per-key model info: discovery + diagnosis
        try:
            detail_map = {}
            # Discovery per-key models
            d_analysis_path = os.path.join(data_dir, "discovery_analysis.jsonl")
            if os.path.exists(d_analysis_path):
                from datetime import datetime as _dt
                with open(d_analysis_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        iso = entry.get("timestamp")
                        try:
                            ts = _dt.fromisoformat(iso).timestamp() if isinstance(iso, str) else None
                        except Exception:
                            ts = None
                        if not ts or ts < cutoff:
                            continue
                        sid = entry.get("scan_id")
                        if not sid:
                            continue
                        lst = detail_map.setdefault(sid, [])
                        lst.append({
                            "element": entry.get("key_name"),
                            "status": entry.get("validation_status") or "unknown",
                            "model_id": entry.get("model_id") or "unknown",
                            "token_usage": entry.get("token_usage"),
                            "error": None
                        })
            # Diagnosis per-key models
            dx_path = os.path.join(data_dir, "diagnosis_analysis.jsonl")
            if os.path.exists(dx_path):
                with open(dx_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        ts = entry.get("timestamp")
                        if not isinstance(ts, (int, float)) or ts < cutoff:
                            continue
                        sid = entry.get("scan_id")
                        if not sid:
                            continue
                        lst = detail_map.setdefault(sid, [])
                        lst.append({
                            "element": entry.get("key_name"),
                            "status": entry.get("status"),
                            "model_id": entry.get("model_id") or "unknown",
                            "token_usage": entry.get("token_usage"),
                            "error": entry.get("error")
                        })
            # Attach to scans
            for sid, rec in scans.items():
                elems = detail_map.get(sid, [])
                rec["elements"] = elems
                # Summary chips
                st = lambda e: (e.get("status") or "").lower()
                ok = sum(1 for e in elems if st(e) in ("success",))
                fallback = sum(1 for e in elems if st(e) in ("degraded_fallback", "fallback"))
                errs = sum(1 for e in elems if st(e) in ("error", "failed", "invalid"))
                rec["summary"] = {"ok": ok, "fallback": fallback, "errors": errs}
        except Exception:
            pass

        # Build list and sort by start_ts desc
        scan_list = list(scans.values())
        scan_list.sort(key=lambda r: (r.get("start_ts") or 0), reverse=True)
        return jsonify({"scans": scan_list}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    # Accept any non-empty key name up to 100 chars (avoid overly strict coupling)
    if not key_name or len(key_name) > 100:
        errors.append("Invalid key name")
    # Accept legacy and new feedback types
    allowed_types = {"too_high", "about_right", "too_low", "accurate", "mixed", "not_accurate"}
    if feedback_type not in allowed_types:
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

        try:
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
        except Exception as e:
            # Log and continue returning success to avoid user-facing 500s for write glitches
            print(f"Warning: feedback write retry also failed: {e}", flush=True)
        return jsonify({"status": "success", "message": "Feedback recorded"}), 200
    except Exception as e:
        print(f"Error handling feedback: {e}", flush=True)
        # Avoid 500s on user action; return success but include note
        return jsonify({"status": "success", "message": "Feedback accepted (delayed write)"}), 200

@app.route("/feedback/discovery", methods=["POST"])
def handle_discovery_feedback():
    """Handle Discovery Mode specific feedback."""
    if not DISCOVERY_MODE_AVAILABLE:
        return jsonify({"status": "error", "message": "Discovery Mode not available"}), 404
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400
        
        # Validate CSRF token
        csrf_token = request.headers.get('X-CSRF-Token') or data.get('csrf_token')
        if not validate_csrf_token(csrf_token):
            return jsonify({"status": "error", "message": "Invalid or missing CSRF token"}), 403
        
        # Validate and record Discovery feedback
        feedback = DiscoveryFeedback(**data)
        success = DiscoveryFeedbackHandler.record_feedback(feedback)
        
        if success:
            return jsonify({"status": "success", "message": "Discovery feedback recorded"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to record feedback"}), 500
            
    except Exception as e:
        print(f"Error handling Discovery feedback: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 400

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

@app.route("/api/features")
def get_features():
    """Get feature flag status for the current user."""
    try:
        user_id = get_user_session_id()
        
        if DISCOVERY_MODE_AVAILABLE:
            return jsonify({
                "discovery_mode": FeatureFlags.is_discovery_enabled(user_id),
                "features": FeatureFlags.get_enabled_features()
            }), 200
        else:
            return jsonify({
                "discovery_mode": False,
                "features": {
                    "discovery_mode": False,
                    "visual_analysis": False,
                    "export_features": False,
                    "advanced_feedback": False
                }
            }), 200
    except Exception as e:
        print(f"Error getting feature status: {e}", flush=True)
        return jsonify({
            "discovery_mode": False,
            "features": {"discovery_mode": False}
        }), 500

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
    mode = data.get("mode", "diagnosis")  # Get mode from request data
    
    if not url:
        emit("scan_update", {"type": "error", "message": "No URL provided."})
        return
    
    # Check if Discovery Mode is requested and available
    if mode == "discovery":
        if not DISCOVERY_MODE_AVAILABLE:
            emit("scan_update", {"type": "error", "message": "Discovery Mode is not available on this server."})
            return
        
        # Check feature flag (get user_id from session)
        if not FeatureFlags.is_discovery_enabled(user_id):
            emit("scan_update", {"type": "error", "message": "Discovery Mode is not enabled for your account."})
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
    
    # Emit initial scan_started message so frontend can capture scan_id (used for Discovery feedback)
    emit("scan_update", {"type": "scan_started", "scan_id": scan_id, "mode": mode}, room=request.sid)
    
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
    
    # Give time for background tasks to notice cancellation (non-blocking for gevent)
    try:
        from gevent import sleep as gevent_sleep
        gevent_sleep(0.1)
    except Exception:
        pass
    
    # Log final stats
    if hasattr(SHARED_CACHE, 'get_stats'):
        print(f"Final cache stats: {SHARED_CACHE.get_stats()}", flush=True)
    
    print("Graceful shutdown complete.", flush=True)
    # Use Werkzeug shutdown if available; otherwise exit
    try:
        from flask import request
        func = request.environ.get('werkzeug.server.shutdown')
        if func:
            func()
    except Exception:
        pass
    os._exit(0)

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
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            dependencies["openai"] = {"status": "not_configured", "message": "API key not set"}
        else:
            # Just validate the API key format and client creation (no actual API call)
            if len(openai_key.strip()) < 20 or not openai_key.startswith('sk-'):
                dependencies["openai"] = {"status": "unhealthy", "error": "Invalid API key format"}
            else:
                try:
                    client = OpenAI(api_key=openai_key)
                    # Client created successfully, assume healthy (avoid costly API calls)
                    dependencies["openai"] = {
                        "status": "healthy", 
                        "note": "API key format valid, client ready"
                    }
                except Exception as client_error:
                    dependencies["openai"] = {"status": "unhealthy", "error": f"Client creation failed: {client_error}"}
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
