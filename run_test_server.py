#!/usr/bin/env python3
"""
Simple test server runner for MemoScan
"""

if __name__ == '__main__':
    from app import app, socketio
    print("🚀 Starting MemoScan test server on http://localhost:8081")
    socketio.run(app, host='0.0.0.0', port=8081, debug=False, allow_unsafe_werkzeug=True)
