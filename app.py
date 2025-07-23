from flask import Flask, render_template
from flask_socketio import SocketIO
from scanner import run_full_scan_stream

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-key!' 
socketio = SocketIO(app, async_mode='gevent')

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_scan')
def handle_scan_request(json):
    url = json.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'type': 'error', 'message': 'URL parameter is missing.'})
        return

    print(f"[WebApp] Received scan request for: {url}")
    
    # This is simpler now - just emit the dictionaries from the generator
    for data_object in run_full_scan_stream(url):
        socketio.emit('scan_update', data_object)

if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
