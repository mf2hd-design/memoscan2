#!/usr/bin/env python3
"""
Final Discovery Mode server - using safe port and minimal complexity
"""
import os
import sys
import time
import threading
import uuid

# Set environment first
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

sys.path.insert(0, '.')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'discovery-key'
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/')
def home():
    """Discovery Mode test interface"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>🔍 MemoScan Discovery Mode</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .mode-selector { margin: 20px 0; }
        .mode-selector label { display: block; margin: 5px 0; padding: 10px; border: 2px solid #ccc; border-radius: 5px; cursor: pointer; }
        .mode-selector input[type="radio"]:checked + span { background: #007acc; color: white; }
        .scan-form { margin: 20px 0; }
        .scan-form input[type="url"] { width: 400px; padding: 8px; margin-right: 10px; }
        .scan-form button { padding: 8px 20px; background: #007acc; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .results { background: #f8f9fa; padding: 15px; border-radius: 5px; max-height: 500px; overflow-y: auto; }
        .message { margin: 5px 0; padding: 8px; border-left: 3px solid #007acc; background: white; }
        .discovery-result { border-left-color: #28a745; background: #d4edda; }
        .error { border-left-color: #dc3545; background: #f8d7da; }
    </style>
</head>
<body>
    <h1>🔍 MemoScan v2 - Discovery Mode Live Test</h1>
    
    <div class="mode-selector">
        <h3>Select Analysis Mode:</h3>
        <label>
            <input type="radio" name="mode" value="diagnosis" checked>
            <span>📊 Diagnosis Mode - Test memorability</span>
        </label>
        <label>
            <input type="radio" name="mode" value="discovery">
            <span>🔍 Discovery Mode - Audit brand strategy</span>
        </label>
    </div>
    
    <div class="scan-form">
        <input type="url" id="urlInput" placeholder="https://apple.com" value="https://apple.com">
        <button onclick="startScan()">Start Analysis</button>
        <button onclick="clearResults()">Clear Results</button>
    </div>
    
    <div id="connection-status">Connecting...</div>
    
    <div class="results" id="results">
        <p><em>Ready for scanning...</em></p>
    </div>
    
    <script>
        const socket = io();
        const results = document.getElementById('results');
        const status = document.getElementById('connection-status');
        
        socket.on('connect', () => {
            status.innerHTML = '✅ Connected to Discovery Mode server';
            status.style.color = 'green';
        });
        
        socket.on('disconnect', () => {
            status.innerHTML = '❌ Disconnected from server';
            status.style.color = 'red';
        });
        
        socket.on('scan_update', (data) => {
            const msgType = data.type || 'unknown';
            let cssClass = 'message';
            
            if (msgType === 'discovery_result') cssClass += ' discovery-result';
            if (msgType === 'error') cssClass += ' error';
            
            const msgDiv = document.createElement('div');
            msgDiv.className = cssClass;
            
            let content = `<strong>${msgType.toUpperCase()}:</strong> `;
            
            if (data.type === 'discovery_result') {
                content += `<strong>${data.key}</strong><br><pre>${JSON.stringify(data.analysis, null, 2)}</pre>`;
            } else {
                content += JSON.stringify(data, null, 2);
            }
            
            msgDiv.innerHTML = content;
            results.appendChild(msgDiv);
            results.scrollTop = results.scrollHeight;
        });
        
        function startScan() {
            const url = document.getElementById('urlInput').value;
            const mode = document.querySelector('input[name="mode"]:checked').value;
            
            if (!url) {
                alert('Please enter a URL');
                return;
            }
            
            results.innerHTML = '<div class="message">🚀 Starting ' + mode + ' scan for: ' + url + '</div>';
            socket.emit('start_scan', {url: url, mode: mode});
        }
        
        function clearResults() {
            results.innerHTML = '<p><em>Results cleared...</em></p>';
        }
    </script>
</body>
</html>
    '''

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "discovery_mode": True, "port": 8081})

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Client connected: {request.sid}")
    emit('connected', {'message': 'Discovery Mode ready'})

@socketio.on('start_scan')
def handle_start_scan(data):
    print(f"🚀 Starting scan: {data}")
    
    url = data.get('url', '')
    mode = data.get('mode', 'diagnosis')
    
    if not url:
        emit('scan_update', {'type': 'error', 'message': 'URL required'})
        return
    
    scan_id = str(uuid.uuid4())
    
    emit('scan_update', {
        'type': 'scan_started',
        'scan_id': scan_id,
        'mode': mode,
        'url': url,
        'timestamp': time.time()
    })
    
    def run_scan():
        try:
            print(f"🔍 Importing scanner for {mode} mode...")
            from scanner import run_full_scan_stream, init_discovery_mode
            
            if mode == 'discovery':
                print("🔧 Initializing Discovery Mode...")
                init_result = init_discovery_mode()
                if not init_result:
                    socketio.emit('scan_update', {
                        'type': 'error',
                        'message': 'Discovery Mode initialization failed'
                    }, room=request.sid)
                    return
                print("✅ Discovery Mode initialized")
            
            cache = {}
            message_count = 0
            discovery_results = []
            
            print(f"📡 Starting {mode} scan pipeline...")
            
            for message in run_full_scan_stream(url, cache, 'en', scan_id, mode):
                message_count += 1
                msg_type = message.get('type', 'unknown')
                
                print(f"📨 Message {message_count}: {msg_type}")
                
                # Track discovery results
                if msg_type == 'discovery_result':
                    discovery_results.append(message)
                    print(f"🎯 Discovery result: {message.get('key', 'unknown')}")
                
                socketio.emit('scan_update', message, room=request.sid)
                
                # Small delay for smooth updates
                time.sleep(0.02)
                
                # Stop after reasonable processing or completion
                if message_count > 30 or msg_type in ['complete', 'error']:
                    break
                
                # If we got some discovery results, continue a bit more
                if len(discovery_results) >= 3:
                    # Let it continue for a few more messages
                    continue
            
            socketio.emit('scan_update', {
                'type': 'scan_complete',
                'scan_id': scan_id,
                'total_messages': message_count,
                'discovery_results': len(discovery_results),
                'mode': mode
            }, room=request.sid)
            
            print(f"✅ Scan completed: {message_count} messages, {len(discovery_results)} discovery results")
            
        except Exception as e:
            print(f"❌ Scan error: {e}")
            import traceback
            traceback.print_exc()
            socketio.emit('scan_update', {
                'type': 'error',
                'message': f'Scan failed: {str(e)}',
                'error_details': str(e)
            }, room=request.sid)
    
    # Run in background thread
    scan_thread = threading.Thread(target=run_scan)
    scan_thread.daemon = True
    scan_thread.start()

if __name__ == '__main__':
    print("🎉 MemoScan Discovery Mode - FINAL TEST SERVER")
    print("🔍 Full Discovery Mode analysis pipeline")
    print("📊 Real-time results with WebSocket")
    print("")
    print("🌐 Open: http://localhost:8081")
    print("❤️  Health: http://localhost:8081/health")
    print("")
    print("🧪 Test both Diagnosis and Discovery modes!")
    print("-" * 50)
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=8081,
        debug=False,
        allow_unsafe_werkzeug=True
    )