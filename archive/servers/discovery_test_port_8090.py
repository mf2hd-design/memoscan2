#!/usr/bin/env python3
"""
Discovery Mode Test Server - Port 8090
Isolated instance with async Playwright fixes for production-quality frontend
"""

import os
import sys
import time
import uuid
from flask import Flask, jsonify, Response
from flask_socketio import SocketIO, emit

# Set environment first
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'

sys.path.insert(0, '.')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'discovery-8090'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def home():
    """Discovery Mode test interface exactly matching production template structure"""
    with open('discovery_mode_frontend_exact.html', 'r') as f:
        frontend_content = f.read()
    
    # Replace the title to indicate this is the port 8090 test server
    frontend_content = frontend_content.replace(
        '<title>MemoScan v2 – Strategic Brand Discovery</title>',
        '<title>🔍 Discovery Mode Test Server - Port 8090</title>'
    )
    
    # Update the header to indicate this is the test server
    frontend_content = frontend_content.replace(
        '<h1>MemoScan v2 – Strategic Brand Discovery</h1>',
        '<h1>🔍 MemoScan v2 – Discovery Mode (Test Server Port 8090)</h1>'
    )
    
    return frontend_content

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "port": 8090,
        "discovery_mode": True,
        "frontend": "production_quality",
        "timestamp": time.time()
    })

@app.route('/screenshot/<screenshot_id>')
def get_screenshot(screenshot_id):
    """Serve screenshot images from the cache - updated route to match production frontend"""
    try:
        # Import the shared cache
        from scanner import SHARED_CACHE
        
        if screenshot_id in SHARED_CACHE:
            cache_item = SHARED_CACHE[screenshot_id]
            if isinstance(cache_item, dict) and cache_item.get('data'):
                import base64
                
                # Decode base64 image data
                image_data = base64.b64decode(cache_item['data'])
                
                return Response(
                    image_data,
                    mimetype=cache_item.get('format', 'image/jpeg'),
                    headers={
                        'Cache-Control': 'public, max-age=3600',
                        'Content-Type': cache_item.get('format', 'image/jpeg')
                    }
                )
        
        # Return 404 if screenshot not found
        return 'Screenshot not found', 404
        
    except Exception as e:
        print(f"Error serving screenshot {screenshot_id}: {e}")
        return 'Error loading screenshot', 500

@socketio.on('start_scan')
def handle_scan(data):
    print(f"🚀 Discovery scan requested on port 8090: {data}")
    
    url = data.get('url', 'https://apple.com')
    scan_id = str(uuid.uuid4())
    
    emit('scan_update', {
        'type': 'status',
        'message': f'Initializing Discovery scan for {url}',
        'progress': 0
    })
    
    # Run scan in a separate thread to avoid threading conflicts
    import threading
    
    def run_scan_thread():
        try:
            # Import and initialize Discovery Mode in the worker thread
            from scanner import run_full_scan_stream, init_discovery_mode
            
            init_success = init_discovery_mode()
            if not init_success:
                socketio.emit('scan_update', {
                    'type': 'error',
                    'message': 'Discovery Mode initialization failed'
                })
                return
                
            socketio.emit('scan_update', {
                'type': 'status',
                'message': 'Discovery Mode components initialized',
                'progress': 5
            })
            
            # Run the scan with isolated cache
            cache = {}
            message_count = 0
            discovery_count = 0
            
            for message in run_full_scan_stream(url, cache, 'en', scan_id, 'discovery'):
                message_count += 1
                
                # Track Discovery results
                if message.get('type') == 'discovery_result':
                    discovery_count += 1
                    print(f"🎯 Discovery result #{discovery_count}: {message.get('key')}")
                
                # Send all messages to frontend using socketio (thread-safe)
                socketio.emit('scan_update', message)
                
                # Stop after completion or max messages
                if message_count >= 80 or message.get('type') in ['complete', 'error']:
                    break
            
            # Send completion status
            socketio.emit('scan_update', {
                'type': 'complete',
                'message': f'Scan finished: {message_count} messages, {discovery_count} Discovery results'
            })
            
            print(f"✅ Scan completed on port 8090: {message_count} messages, {discovery_count} Discovery results")
            
        except Exception as e:
            print(f"❌ Scan error on port 8090: {e}")
            import traceback
            traceback.print_exc()
            socketio.emit('scan_update', {
                'type': 'error',
                'message': f'Scan failed: {str(e)}'
            })
    
    # Start the scan in a background thread
    scan_thread = threading.Thread(target=run_scan_thread)
    scan_thread.daemon = True
    scan_thread.start()

if __name__ == '__main__':
    print("🎉 DISCOVERY MODE TEST SERVER - PORT 8090")
    print("=" * 50)
    print("🔍 Configuration:")
    print("   ✅ Production-quality MemoScan v2 frontend design")
    print("   ✅ GPT-5 Discovery analysis with visual enhancements")
    print("   ✅ Async Playwright API for threading compatibility")
    print("   ✅ Threading mode for improved stability")
    print("   ✅ Visual-text alignment with 1000 char justification")
    print("   ✅ Isolated port to avoid conflicts")
    print()
    print("🌐 Server URL: http://localhost:8090")
    print("🎨 Frontend: discovery_mode_frontend_exact.html")
    print("🧪 Ready for comprehensive Discovery Mode testing!")
    print("=" * 50)
    
    socketio.run(
        app,
        host='0.0.0.0',  # Bind to all interfaces
        port=8090,
        debug=False,
        allow_unsafe_werkzeug=True
    )