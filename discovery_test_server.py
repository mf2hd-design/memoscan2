#!/usr/bin/env python3
"""
Discovery Mode Test Server - Full functionality without SocketIO complexity
"""
import os
import sys
import json
import time
import uuid
from flask import Flask, request, render_template, jsonify, redirect

# Set up environment
os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'

# Add current directory to path
sys.path.insert(0, '.')

app = Flask(__name__, template_folder='templates')

@app.route('/')
def home():
    """Main page with Discovery Mode selector"""
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
    """Return a CSRF token"""
    return jsonify({"csrf_token": f"test-token-{int(time.time())}"})

@app.route('/test-discovery-scan')
def test_discovery_scan():
    """Test Discovery Mode scanning with a sample URL"""
    url = request.args.get('url', 'https://apple.com')
    mode = request.args.get('mode', 'discovery')
    
    if mode != 'discovery':
        return redirect('/')
    
    print(f"🔍 Testing Discovery Mode scan for: {url}")
    
    try:
        # Import scanner
        from scanner import run_full_scan_stream, init_discovery_mode
        
        # Initialize Discovery Mode
        init_result = init_discovery_mode()
        if not init_result:
            return jsonify({'error': 'Discovery Mode initialization failed'})
        
        # Create scan cache
        cache = {}
        scan_id = str(uuid.uuid4())
        
        # Run Discovery scan (collect first few results)
        scan_results = []
        message_count = 0
        
        print(f"🚀 Starting Discovery scan: {url}")
        
        for message in run_full_scan_stream(url, cache, 'en', scan_id, 'discovery'):
            scan_results.append(message)
            message_count += 1
            
            # Stop after getting some meaningful results or error
            if message_count >= 20 or message.get('type') in ['error', 'complete']:
                break
                
            # Stop if we get discovery results
            if message.get('type') == 'discovery_result':
                # Get a few more messages for completeness
                for i, additional_msg in enumerate(run_full_scan_stream(url, cache, 'en', scan_id, 'discovery')):
                    if i >= 5:
                        break
                    scan_results.append(additional_msg)
                break
        
        print(f"✅ Collected {len(scan_results)} messages from Discovery scan")
        
        # Return results as HTML page
        results_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Discovery Mode Test Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; max-width: 1000px; margin: 0 auto; padding: 20px; }}
        .message {{ margin: 10px 0; padding: 15px; border-left: 4px solid #007acc; background: #f8f9fa; }}
        .discovery-result {{ border-left-color: #28a745; background: #d4edda; }}
        .error {{ border-left-color: #dc3545; background: #f8d7da; }}
        .metadata {{ color: #666; font-size: 0.9em; }}
        h1 {{ color: #007acc; }}
        .back-link {{ display: inline-block; margin: 20px 0; padding: 10px 20px; background: #007acc; color: white; text-decoration: none; border-radius: 5px; }}
        pre {{ background: #f1f1f1; padding: 10px; border-radius: 4px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>🔍 Discovery Mode Test Results</h1>
    <p><strong>URL:</strong> {url}</p>
    <p><strong>Mode:</strong> {mode}</p>
    <p><strong>Scan ID:</strong> {scan_id}</p>
    <p><strong>Messages Collected:</strong> {len(scan_results)}</p>
    
    <a href="/" class="back-link">← Back to Mode Selector</a>
    
    <h2>📊 Scan Messages:</h2>
"""
        
        for i, message in enumerate(scan_results):
            msg_type = message.get('type', 'unknown')
            css_class = 'discovery-result' if msg_type == 'discovery_result' else ('error' if msg_type == 'error' else 'message')
            
            results_html += f"""
    <div class="message {css_class}">
        <div class="metadata">Message {i+1} | Type: {msg_type}</div>
        <pre>{json.dumps(message, indent=2)}</pre>
    </div>
"""
        
        results_html += """
    <a href="/" class="back-link">← Back to Mode Selector</a>
</body>
</html>
"""
        
        return results_html
        
    except Exception as e:
        print(f"❌ Discovery scan failed: {e}")
        import traceback
        traceback.print_exc()
        
        return f"""
<!DOCTYPE html>
<html>
<head><title>Discovery Mode Error</title></head>
<body style="font-family: Arial; padding: 20px;">
    <h1>❌ Discovery Mode Error</h1>
    <p><strong>URL:</strong> {url}</p>
    <p><strong>Error:</strong> {str(e)}</p>
    <pre>{traceback.format_exc()}</pre>
    <a href="/" style="display: inline-block; margin: 20px 0; padding: 10px 20px; background: #007acc; color: white; text-decoration: none;">← Back to Mode Selector</a>
</body>
</html>
"""

@app.route('/quick-discovery-test')
def quick_discovery_test():
    """Quick Discovery Mode test page"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Quick Discovery Mode Test</title>
    <style>body { font-family: Arial; padding: 20px; max-width: 600px; margin: 0 auto; }</style>
</head>
<body>
    <h1>🔍 Quick Discovery Mode Test</h1>
    <p>Test Discovery Mode scanning with these URLs:</p>
    
    <ul>
        <li><a href="/test-discovery-scan?url=https://apple.com&mode=discovery">🍎 Test Apple.com</a></li>
        <li><a href="/test-discovery-scan?url=https://nike.com&mode=discovery">👟 Test Nike.com</a></li>
        <li><a href="/test-discovery-scan?url=https://airbnb.com&mode=discovery">🏠 Test Airbnb.com</a></li>
    </ul>
    
    <p>Or enter a custom URL:</p>
    <form action="/test-discovery-scan" method="get">
        <input type="hidden" name="mode" value="discovery">
        <input type="url" name="url" placeholder="https://example.com" style="width: 300px; padding: 8px;">
        <input type="submit" value="Test Discovery Mode" style="padding: 8px 16px; background: #007acc; color: white; border: none; cursor: pointer;">
    </form>
    
    <br><a href="/">← Back to Main Interface</a>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 Starting MemoScan v2 with LIVE Discovery Mode Testing")
    print("📊 Full Discovery Mode scanning functionality")
    print("🔍 Real brand analysis with positioning themes, key messages, tone of voice")
    print("")
    print("🌐 Main Interface: http://localhost:8000")
    print("⚡ Quick Test: http://localhost:8000/quick-discovery-test")
    print("")
    print("Note: This uses the full MemoScan scanning engine!")
    
    app.run(
        host='127.0.0.1',
        port=8000,
        debug=False,
        threaded=True
    )