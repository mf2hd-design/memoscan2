#!/usr/bin/env python3
"""
Working Discovery Mode server - built incrementally
"""
import os
import sys
import time
import threading
import uuid

# Set environment first
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

# Add current directory to path
sys.path.insert(0, '.')

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'discovery-test-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Track active scans
active_scans = {}

@app.route('/')
def home():
    """Serve the main Discovery Mode interface"""
    try:
        return render_template('index_production.html')
    except Exception as e:
        return f'''
        <h1>🔍 MemoScan Discovery Mode</h1>
        <p>Template error: {e}</p>
        <p>Discovery Mode backend is working!</p>
        <p><a href="/test-ui">Try Test UI</a></p>
        '''

@app.route('/test-ui')
def test_ui():
    """Fallback test UI"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Discovery Mode Test</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
</head>
<body style="font-family: Arial; padding: 20px;">
    <h1>🔍 Discovery Mode Test Interface</h1>
    
    <div>
        <h3>Mode Selection:</h3>
        <label>
            <input type="radio" name="mode" value="diagnosis" checked> 📊 Diagnosis Mode
        </label><br>
        <label>
            <input type="radio" name="mode" value="discovery"> 🔍 Discovery Mode
        </label>
    </div>
    
    <div style="margin: 20px 0;">
        <input type="url" id="urlInput" placeholder="https://apple.com" style="width: 300px; padding: 8px;">
        <button onclick="startScan()" style="padding: 8px 16px;">Start Scan</button>
    </div>
    
    <div id="results" style="margin-top: 20px; padding: 10px; background: #f5f5f5; min-height: 100px;">
        <p>Ready for testing...</p>
    </div>
    
    <script>
        const socket = io();
        const results = document.getElementById('results');
        
        socket.on('connect', () => {
            results.innerHTML += '<p>✅ Connected to server</p>';
        });
        
        socket.on('scan_update', (data) => {
            results.innerHTML += `<p><strong>${data.type}:</strong> ${JSON.stringify(data)}</p>`;
            results.scrollTop = results.scrollHeight;
        });
        
        function startScan() {
            const url = document.getElementById('urlInput').value;
            const mode = document.querySelector('input[name="mode"]:checked').value;
            
            results.innerHTML = '<p>🚀 Starting scan...</p>';
            socket.emit('start_scan', {url: url, mode: mode});
        }
    </script>
</body>
</html>
    '''

@app.route('/api/features')
def get_features():
    """Return feature flags"""
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
    return jsonify({"csrf_token": f"token-{int(time.time())}"})

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "discovery_mode": True,
        "active_scans": len(active_scans),
        "timestamp": time.time()
    })

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to Discovery Mode server'})

@socketio.on('start_scan')
def handle_start_scan(data):
    print(f"🚀 Scan request: {data}")
    
    url = data.get('url', '')
    mode = data.get('mode', 'diagnosis')
    
    if not url:
        emit('scan_update', {'type': 'error', 'message': 'URL required'})
        return
    
    scan_id = str(uuid.uuid4())
    active_scans[scan_id] = {'url': url, 'mode': mode, 'start': time.time()}
    
    emit('scan_update', {
        'type': 'scan_started',
        'scan_id': scan_id,
        'mode': mode,
        'url': url
    })
    
    def run_discovery_scan():
        try:
            # Import scanner only when needed
            from scanner import run_full_scan_stream, init_discovery_mode
            
            # Initialize Discovery Mode
            if mode == 'discovery':
                init_result = init_discovery_mode()
                if not init_result:
                    socketio.emit('scan_update', {
                        'type': 'error',
                        'message': 'Discovery Mode initialization failed'
                    }, room=request.sid)
                    return
            
            # Run the scan
            cache = {}
            message_count = 0
            
            for message in run_full_scan_stream(url, cache, 'en', scan_id, mode):
                message_count += 1
                print(f"📨 Message {message_count}: {message.get('type', 'unknown')}")
                
                socketio.emit('scan_update', message, room=request.sid)
                time.sleep(0.05)  # Small delay for real-time feel
                
                # Stop after reasonable time or completion
                if message_count > 50 or message.get('type') in ['complete', 'error']:
                    break
            
            # Cleanup
            if scan_id in active_scans:
                del active_scans[scan_id]
            
            socketio.emit('scan_update', {
                'type': 'scan_finished',
                'scan_id': scan_id,
                'messages_processed': message_count
            }, room=request.sid)
            
        except Exception as e:
            print(f"❌ Scan error: {e}")
            socketio.emit('scan_update', {
                'type': 'error',
                'message': f'Scan failed: {str(e)}'
            }, room=request.sid)
    
    # Run scan in background
    scan_thread = threading.Thread(target=run_discovery_scan)
    scan_thread.daemon = True
    scan_thread.start()

if __name__ == '__main__':
    print("🎉 MemoScan Discovery Mode - Working Server")
    print("🔍 Full Discovery Mode scanning enabled")
    print("📊 Real-time WebSocket updates")
    print("")
    print("🌐 Main UI: http://localhost:8080")
    print("🧪 Test UI: http://localhost:8080/test-ui")
    print("❤️  Health: http://localhost:8080/health")
    print("")
    print("Ready for Discovery Mode testing!")
    print("-" * 50)
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=8080,
        debug=False,
        allow_unsafe_werkzeug=True
    )