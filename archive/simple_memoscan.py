#!/usr/bin/env python3
"""
Simplified MemoScan server for testing Discovery Mode UI
"""
import os
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'

from flask import Flask, render_template, jsonify

app = Flask(__name__, template_folder='templates')

@app.route('/')
def home():
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
    """Return a dummy CSRF token for testing"""
    return jsonify({"csrf_token": "test-token-123"})

if __name__ == '__main__':
    print("🚀 Starting MemoScan v2 - Discovery Mode Test")
    print("📊 Mode selector will be visible")
    print("🔍 Discovery Mode UI ready for testing")
    print("")
    print("🌐 Open: http://localhost:9000")
    print("")
    
    app.run(
        host='127.0.0.1',
        port=9000,
        debug=True,
        threaded=True
    )