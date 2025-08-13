#!/usr/bin/env python3
"""
Clean Discovery Mode server without complex app.py dependencies
"""
import os
import sys
import json
import time
import uuid
import threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

# Set environment variables FIRST
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'

sys.path.insert(0, '.')

# Import minimal scanner without the full app
from scanner import run_full_scan_stream, init_discovery_mode

# Create Flask app
app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'dev-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Discovery Mode
print("🔧 Initializing Discovery Mode...")
init_result = init_discovery_mode()
print(f"✅ Discovery Mode initialized: {init_result}")

@app.route('/')
def home():
    """Main page with Discovery Mode"""
    return render_template('index_production.html')

@app.route('/api/features')
def get_features():
    """Return Discovery Mode feature status"""
    return jsonify({
        "discovery_mode": True,
        "features": {
            "discovery_mode": True,
            "visual_analysis": False,
            "export_features": False,
            "advanced_feedback": False
        }
    })

@app.route('/csrf-token')
def csrf_token():
    """Return CSRF token"""
    return jsonify({"csrf_token": f"token-{int(time.time())}"})

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "discovery_mode": "enabled",
        "timestamp": time.time(),
        "features_working": True
    })

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Client connected: {request.sid}")
    emit('connected', {'data': 'Connected to MemoScan Discovery Mode'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Client disconnected: {request.sid}")

@socketio.on('start_scan')
def handle_start_scan(data):
    """Handle scan requests with Discovery Mode support"""
    print(f"🚀 Scan request received: {data}")
    
    url = data.get('url', '')
    mode = data.get('mode', 'diagnosis')
    
    if not url:
        emit('scan_update', {'type': 'error', 'message': 'No URL provided'})
        return
    
    print(f"🔍 Starting {mode} scan for: {url}")
    
    # Start background scan
    def run_scan():
        try:
            scan_id = str(uuid.uuid4())
            cache = {}
            
            for message in run_full_scan_stream(url, cache, 'en', scan_id, mode):
                print(f"📨 Sending: {message.get('type', 'unknown')}")
                socketio.emit('scan_update', message, room=request.sid)
                
                # Add small delay to prevent overwhelming the client
                time.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Scan error: {e}")
            socketio.emit('scan_update', {
                'type': 'error',
                'message': f'Scan failed: {str(e)}'
            }, room=request.sid)
    
    # Run scan in background thread
    scan_thread = threading.Thread(target=run_scan)
    scan_thread.daemon = True
    scan_thread.start()
    
    emit('scan_update', {
        'type': 'scan_started',
        'mode': mode,
        'message': f'Starting {mode} analysis...'
    })

if __name__ == '__main__':
    print("🚀 MemoScan v2 - Clean Discovery Mode Server")
    print("🔍 Full Discovery Mode functionality enabled")
    print("📊 Real-time scanning with WebSocket support")
    print("")
    print("🌐 Open: http://localhost:7777")
    print("🔍 Discovery Mode: ENABLED")
    print("📊 Health: http://localhost:7777/health")
    print("")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        socketio.run(
            app,
            host='127.0.0.1',
            port=7777,
            debug=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()