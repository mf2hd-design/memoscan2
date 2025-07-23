from flask import Flask, render_template, request, Response
from scanner import run_full_scan_stream

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan")
def scan():
    url = request.args.get("url", "").strip()

    def _generate():
        if not url:
            yield "data: [ERROR] URL parameter is missing.\\n\\n"
            return

        print(f"[WebApp] Received scan request for: {url}")
        for data in run_full_scan_stream(url):
            yield data

    headers = {
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache",
    }
    return Response(_generate(), mimetype="text/event-stream", headers=headers)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
