from flask import Flask, render_template
from flask_socketio import SocketIO
from scanner import run_full_scan_stream

app = Flask(__name__)
# The secret key is needed for session management, which SocketIO uses under the hood.
app.config['SECRET_KEY'] = 'your-very-secret-key!' 

# Initialize SocketIO, telling it to use the gevent async mode.
# This is critical for it to work with our Gunicorn setup.
socketio = SocketIO(app, async_mode='gevent')

@app.route("/")
def index():
    return render_template("index.html")

# This event is triggered when a user's browser connects.
@socketio.on('connect')
def handle_connect():
    print('Client connected')

# This event is triggered when a user's browser disconnects.
@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# This is our main event handler, replacing the old '/scan' route.
# The browser will emit a 'start_scan' event to trigger this.
@socketio.on('start_scan')
def handle_scan_request(json):
    url = json.get('url', '').strip()
    if not url:
        socketio.emit('scan_update', {'data': '[ERROR] URL parameter is missing.'})
        return

    print(f"[WebApp] Received scan request for: {url}")
    
    # We can now loop through our existing generator and 'emit' each result.
    for data in run_full_scan_stream(url):
        # We wrap the raw data in a simple JSON structure.
        socketio.emit('scan_update', {'data': data})

# This is used for local development. When deployed on Render, Gunicorn runs the app.
if __name__ == '__main__':
    socketio.run(app, debug=True, host="0.0.0.0", port=10000)
