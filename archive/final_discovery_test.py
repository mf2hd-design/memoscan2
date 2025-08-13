#!/usr/bin/env python3
"""
Final Discovery Mode Test Server - Minimal implementation
"""
import os
import sys
import time
import uuid
from flask import Flask
from flask_socketio import SocketIO, emit

# Set environment first
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'

sys.path.insert(0, '.')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'discovery-test'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def home():
    """Simple Discovery test page"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Discovery Mode - Final Test</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .connected { background: #d4edda; color: #155724; }
        .scanning { background: #fff3cd; color: #856404; }
        .results { background: #f8f9fa; padding: 15px; border-radius: 5px; max-height: 500px; overflow-y: auto; }
        .discovery-result { background: #d4edda; padding: 10px; margin: 5px 0; border-radius: 3px; }
        input[type="url"] { width: 300px; padding: 8px; margin-right: 10px; }
        button { padding: 8px 15px; background: #007acc; color: white; border: none; border-radius: 3px; }
    </style>
</head>
<body>
    <h1>🔍 Discovery Mode - Final Test</h1>
    <p>Testing Discovery Mode with GPT-5 integration</p>
    
    <div>
        <input type="url" id="url" value="https://bmwgroup.com" placeholder="Enter URL">
        <button onclick="startScan()">Start Discovery Scan</button>
    </div>
    
    <div id="status" class="status">Connecting...</div>
    <div id="results" class="results">Ready for scan...</div>
    
    <script>
        const socket = io();
        const status = document.getElementById('status');
        const results = document.getElementById('results');
        
        socket.on('connect', () => {
            status.innerHTML = '✅ Connected - Discovery Mode Ready';
            status.className = 'status connected';
        });
        
        socket.on('scan_update', (data) => {
            const div = document.createElement('div');
            
            if (data.type === 'discovery_result') {
                div.className = 'discovery-result';
                div.innerHTML = `<strong>🎯 DISCOVERY: ${data.key}</strong><br><pre>${JSON.stringify(data.analysis, null, 2)}</pre>`;
            } else if (data.type === 'error') {
                div.style.background = '#f8d7da';
                div.innerHTML = `❌ ${data.message}`;
            } else {
                div.innerHTML = `📊 ${data.type}: ${data.message || JSON.stringify(data)}`;
            }
            
            results.appendChild(div);
            results.scrollTop = results.scrollHeight;
        });
        
        function startScan() {
            const url = document.getElementById('url').value;
            status.innerHTML = '🚀 Starting Discovery scan...';
            status.className = 'status scanning';
            results.innerHTML = '';
            socket.emit('start_scan', {url: url, mode: 'discovery'});
        }
    </script>
</body>
</html>
    '''

@socketio.on('start_scan')
def handle_scan(data):
    print(f"🚀 Discovery scan requested: {data}")
    
    url = data.get('url', 'https://bmwgroup.com')
    scan_id = str(uuid.uuid4())
    
    emit('scan_update', {'type': 'status', 'message': f'Starting Discovery scan for {url}'})
    
    try:
        # Import and run Discovery scan
        from scanner import run_full_scan_stream, init_discovery_mode
        
        # Initialize Discovery Mode
        init_success = init_discovery_mode()
        if not init_success:
            emit('scan_update', {'type': 'error', 'message': 'Discovery Mode initialization failed'})
            return
            
        emit('scan_update', {'type': 'status', 'message': 'Discovery Mode initialized successfully'})
        
        # Run the scan with Discovery mode
        cache = {}
        message_count = 0
        discovery_count = 0
        
        for message in run_full_scan_stream(url, cache, 'en', scan_id, 'discovery'):
            message_count += 1
            
            # Track Discovery results
            if message.get('type') == 'discovery_result':
                discovery_count += 1
                print(f"🎯 Discovery result #{discovery_count}: {message.get('key')}")
            
            # Send to frontend
            emit('scan_update', message)
            
            # Stop after reasonable processing or completion
            if message_count >= 60 or message.get('type') in ['complete', 'error']:
                break
        
        # Final status
        emit('scan_update', {
            'type': 'complete', 
            'message': f'Scan completed: {message_count} messages, {discovery_count} Discovery results'
        })
        
        print(f"✅ Scan completed: {message_count} messages, {discovery_count} Discovery results")
        
    except Exception as e:
        print(f"❌ Scan error: {e}")
        emit('scan_update', {'type': 'error', 'message': f'Scan failed: {str(e)}'})

if __name__ == '__main__':
    print("🎉 FINAL DISCOVERY MODE TEST SERVER")
    print("🔍 All fixes applied:")
    print("   ✅ GPT-5 parameters corrected")
    print("   ✅ API key configured")
    print("   ✅ Message limits increased")
    print("   ✅ Error handling fixed")
    print()
    print("🌐 Server: http://localhost:8085")
    print("🧪 Test Discovery Mode with real GPT-5 analysis!")
    print("-" * 50)
    
    socketio.run(
        app,
        host='127.0.0.1',
        port=8085,
        debug=False,
        allow_unsafe_werkzeug=True
    )