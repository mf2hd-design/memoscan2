#!/usr/bin/env python3
"""
Robust Discovery Mode server startup script
"""
import os
import sys
import time
import signal

# Set environment variables
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'

sys.path.insert(0, '.')

def signal_handler(signum, frame):
    print("\n🛑 Shutting down server...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

try:
    print("🔍 Testing basic imports...")
    from flask import Flask, render_template, jsonify
    print("✅ Flask imported successfully")
    
    from scanner import run_full_scan_stream, init_discovery_mode
    print("✅ Scanner imported successfully")
    
    # Initialize Discovery Mode
    print("🔧 Initializing Discovery Mode...")
    init_result = init_discovery_mode()
    print(f"✅ Discovery Mode initialized: {init_result}")
    
    # Create Flask app
    app = Flask(__name__, template_folder='templates')
    
    @app.route('/')
    def home():
        return render_template('index_production.html')
    
    @app.route('/api/features')
    def get_features():
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
        return jsonify({"csrf_token": f"test-token-{int(time.time())}"})
    
    @app.route('/health')
    def health():
        return jsonify({"status": "ok", "discovery_mode": "enabled", "timestamp": time.time()})
    
    print("🚀 Starting MemoScan v2 with Discovery Mode...")
    print("🌐 URL: http://localhost:9999")
    print("🔍 Discovery Mode: ENABLED")
    print("📊 Health Check: http://localhost:9999/health")
    print("💡 Press Ctrl+C to stop")
    print("-" * 50)
    
    # Start the server
    app.run(
        host='0.0.0.0',  # Bind to all interfaces
        port=9999,
        debug=False,
        use_reloader=False,
        threaded=True
    )
    
except KeyboardInterrupt:
    print("\n🛑 Server stopped by user")
except Exception as e:
    print(f"❌ Server startup failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)