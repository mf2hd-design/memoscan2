#!/usr/bin/env python3
"""
Reliable Discovery Mode server - fixes WebSocket threading issues
"""
import os
import sys
import time
import uuid
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit

# Set environment first
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'

sys.path.insert(0, '.')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'discovery-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Store client sessions
active_sessions = {}

@app.route('/')
def home():
    """Discovery Mode test interface"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>🔍 MemoScan Discovery Mode - Fixed</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; }
        .mode-selector { margin: 20px 0; padding: 20px; border: 2px solid #e0e0e0; border-radius: 8px; }
        .mode-selector h3 { margin-top: 0; }
        .mode-selector label { 
            display: block; margin: 10px 0; padding: 15px; border: 2px solid #ccc; 
            border-radius: 5px; cursor: pointer; transition: all 0.3s ease;
        }
        .mode-selector label:hover { border-color: #007acc; background: #f0f8ff; }
        .mode-selector input[type="radio"]:checked + span { 
            background: #007acc; color: white; padding: 5px 10px; border-radius: 4px;
        }
        .scan-form { margin: 20px 0; text-align: center; }
        .scan-form input[type="url"] { 
            width: 400px; padding: 10px; margin-right: 10px; font-size: 16px;
            border: 2px solid #ccc; border-radius: 4px;
        }
        .scan-form button { 
            padding: 10px 20px; background: #007acc; color: white; border: none; 
            border-radius: 4px; cursor: pointer; font-size: 16px;
        }
        .scan-form button:disabled { background: #ccc; cursor: not-allowed; }
        .status { margin: 20px 0; padding: 10px; text-align: center; font-weight: bold; }
        .status.connected { background: #d4edda; color: #155724; border-radius: 4px; }
        .status.scanning { background: #fff3cd; color: #856404; border-radius: 4px; }
        .status.error { background: #f8d7da; color: #721c24; border-radius: 4px; }
        .results { 
            background: #f8f9fa; padding: 20px; border-radius: 8px; 
            max-height: 600px; overflow-y: auto; margin-top: 20px;
        }
        .message { 
            margin: 8px 0; padding: 12px; border-left: 4px solid #007acc; 
            background: white; border-radius: 4px; font-family: monospace;
        }
        .discovery-result { 
            border-left-color: #28a745; background: #d4edda; 
            font-family: Arial; padding: 15px;
        }
        .discovery-result h4 { margin: 0 0 10px 0; color: #155724; }
        .error { border-left-color: #dc3545; background: #f8d7da; color: #721c24; }
        .progress { border-left-color: #17a2b8; background: #d1ecf1; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 MemoScan v2 - Discovery Mode</h1>
        <p>Test the complete Discovery Mode integration with real-time results</p>
    </div>
    
    <div class="mode-selector">
        <h3>🎯 Select Analysis Mode:</h3>
        <label>
            <input type="radio" name="mode" value="diagnosis" checked>
            <span>📊 Diagnosis Mode</span> - Analyze memorability and engagement
        </label>
        <label>
            <input type="radio" name="mode" value="discovery">
            <span>🔍 Discovery Mode</span> - Discover positioning, messages, and tone
        </label>
    </div>
    
    <div class="scan-form">
        <input type="url" id="urlInput" placeholder="https://apple.com" value="https://apple.com">
        <button id="scanBtn" onclick="startScan()">Start Analysis</button>
        <button onclick="clearResults()">Clear Results</button>
    </div>
    
    <div id="status" class="status">Connecting to server...</div>
    
    <div class="results" id="results">
        <p><em>Ready for scanning. Select a mode and click "Start Analysis".</em></p>
    </div>
    
    <script>
        const socket = io();
        const results = document.getElementById('results');
        const status = document.getElementById('status');
        const scanBtn = document.getElementById('scanBtn');
        
        let isScanning = false;
        
        socket.on('connect', () => {
            status.innerHTML = '✅ Connected to Discovery Mode server';
            status.className = 'status connected';
        });
        
        socket.on('disconnect', () => {
            status.innerHTML = '❌ Disconnected from server';
            status.className = 'status error';
        });
        
        socket.on('scan_update', (data) => {
            const msgType = data.type || 'unknown';
            console.log('Received:', msgType, data);
            
            let cssClass = 'message';
            let content = '';
            
            if (msgType === 'scan_started') {
                status.innerHTML = '🚀 Scan started - processing...';
                status.className = 'status scanning';
                content = `🚀 <strong>SCAN STARTED</strong><br>Mode: ${data.mode}<br>URL: ${data.url}<br>ID: ${data.scan_id}`;
                
            } else if (msgType === 'discovery_result') {
                cssClass = 'message discovery-result';
                const key = data.key || 'unknown';
                content = `<h4>🎯 DISCOVERY RESULT: ${key.toUpperCase()}</h4>`;
                content += `<pre>${JSON.stringify(data.analysis, null, 2)}</pre>`;
                
            } else if (msgType === 'error') {
                cssClass = 'message error';
                content = `❌ <strong>ERROR:</strong> ${data.message}`;
                status.innerHTML = '❌ Scan failed';
                status.className = 'status error';
                isScanning = false;
                scanBtn.disabled = false;
                scanBtn.innerHTML = 'Start Analysis';
                
            } else if (msgType === 'scan_complete') {
                status.innerHTML = '✅ Scan completed successfully';
                status.className = 'status connected';
                content = `✅ <strong>SCAN COMPLETED</strong><br>Messages: ${data.total_messages}<br>Discovery Results: ${data.discovery_results}`;
                isScanning = false;
                scanBtn.disabled = false;
                scanBtn.innerHTML = 'Start Analysis';
                
            } else if (msgType === 'status' || msgType === 'activity') {
                cssClass = 'message progress';
                content = `📊 ${data.message || JSON.stringify(data)}`;
                
            } else {
                content = `📨 <strong>${msgType.toUpperCase()}:</strong><br><pre>${JSON.stringify(data, null, 2)}</pre>`;
            }
            
            const msgDiv = document.createElement('div');
            msgDiv.className = cssClass;
            msgDiv.innerHTML = content;
            results.appendChild(msgDiv);
            results.scrollTop = results.scrollHeight;
        });
        
        function startScan() {
            if (isScanning) return;
            
            const url = document.getElementById('urlInput').value;
            const mode = document.querySelector('input[name="mode"]:checked').value;
            
            if (!url) {
                alert('Please enter a URL');
                return;
            }
            
            isScanning = true;
            scanBtn.disabled = true;
            scanBtn.innerHTML = '⏳ Scanning...';
            
            results.innerHTML = `<div class="message progress">🚀 Starting ${mode} scan for: ${url}</div>`;
            socket.emit('start_scan', {url: url, mode: mode});
        }
        
        function clearResults() {
            results.innerHTML = '<p><em>Results cleared...</em></p>';
            status.innerHTML = '✅ Connected to Discovery Mode server';
            status.className = 'status connected';
        }
        
        // Auto-scroll to bottom when new results appear
        const observer = new MutationObserver(() => {
            results.scrollTop = results.scrollHeight;
        });
        observer.observe(results, { childList: true });
    </script>
</body>
</html>
    '''

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "discovery_mode": True, 
        "port": 8082,
        "active_sessions": len(active_sessions),
        "timestamp": time.time()
    })

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Client connected: {request.sid}")
    active_sessions[request.sid] = {'connected': time.time()}
    emit('connected', {'message': 'Discovery Mode ready'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"🔌 Client disconnected: {request.sid}")
    if request.sid in active_sessions:
        del active_sessions[request.sid]

@socketio.on('start_scan')
def handle_start_scan(data):
    print(f"🚀 Scan request from {request.sid}: {data}")
    
    url = data.get('url', '')
    mode = data.get('mode', 'diagnosis')
    
    if not url:
        emit('scan_update', {'type': 'error', 'message': 'URL required'})
        return
    
    scan_id = str(uuid.uuid4())
    client_id = request.sid
    
    # Store scan info
    active_sessions[client_id]['current_scan'] = {
        'scan_id': scan_id,
        'url': url, 
        'mode': mode,
        'started': time.time()
    }
    
    emit('scan_update', {
        'type': 'scan_started',
        'scan_id': scan_id,
        'mode': mode,
        'url': url,
        'timestamp': time.time()
    })
    
    # Run scan synchronously to avoid threading issues
    try:
        print(f"🔍 Starting {mode} scan synchronously...")
        
        # Import scanner
        from scanner import run_full_scan_stream, init_discovery_mode
        
        if mode == 'discovery':
            print("🔧 Initializing Discovery Mode...")
            init_result = init_discovery_mode()
            if not init_result:
                emit('scan_update', {
                    'type': 'error',
                    'message': 'Discovery Mode initialization failed'
                })
                return
            print("✅ Discovery Mode initialized")
        
        cache = {}
        message_count = 0
        discovery_results = 0
        
        print(f"📡 Starting scan pipeline for {url}...")
        
        # Process scan messages
        for message in run_full_scan_stream(url, cache, 'en', scan_id, mode):
            message_count += 1
            msg_type = message.get('type', 'unknown')
            
            print(f"📨 Message {message_count}: {msg_type}")
            
            # Track discovery results
            if msg_type == 'discovery_result':
                discovery_results += 1
                print(f"🎯 Discovery result #{discovery_results}: {message.get('key', 'unknown')}")
            
            # Send to client
            socketio.emit('scan_update', message, room=client_id)
            
            # Allow more messages to reach Discovery analysis phase
            if message_count >= 60 or msg_type in ['complete', 'error']:
                break
        
        # Send completion message
        socketio.emit('scan_update', {
            'type': 'scan_complete',
            'scan_id': scan_id,
            'total_messages': message_count,
            'discovery_results': discovery_results,
            'mode': mode
        }, room=client_id)
        
        print(f"✅ Scan completed: {message_count} messages, {discovery_results} discovery results")
        
    except Exception as e:
        print(f"❌ Scan error: {e}")
        import traceback
        traceback.print_exc()
        
        socketio.emit('scan_update', {
            'type': 'error',
            'message': f'Scan failed: {str(e)}',
            'error_details': str(e)
        }, room=client_id)

if __name__ == '__main__':
    print("🎉 MemoScan Discovery Mode - RELIABLE SERVER")
    print("🔧 Fixed WebSocket threading issues")
    print("📊 Synchronous processing for reliability")
    print("")
    print("🌐 Open: http://localhost:8082")
    print("❤️  Health: http://localhost:8082/health")
    print("")
    print("🧪 Test Discovery Mode with real-time updates!")
    print("-" * 50)
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=8082,
        debug=False,
        allow_unsafe_werkzeug=True
    )