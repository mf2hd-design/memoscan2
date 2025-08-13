#!/usr/bin/env python3
"""
Minimal test server to verify local connectivity works
"""
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return '''
    <h1>🎉 Test Server Working!</h1>
    <p>If you can see this, local Flask servers work fine.</p>
    <p>The issue was likely with the complex MemoScan setup.</p>
    '''

@app.route('/test')
def test():
    return {'status': 'OK', 'message': 'Test endpoint working'}

if __name__ == '__main__':
    print("🧪 Starting minimal test server...")
    print("📁 Open: http://localhost:6000")
    app.run(
        host='127.0.0.1',
        port=6000,
        debug=True,
        threaded=True
    )