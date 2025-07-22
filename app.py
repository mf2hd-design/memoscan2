import asyncio
from flask import Flask, render_template, request, Response
from scanner import run_full_scan_stream

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan")
def scan():
    url = request.args.get("url", "").strip()
    if not url:
        return Response("data: [ERROR] URL parameter is missing.\\n\\n", mimetype="text/event-stream")

    print(f"[WebApp] Received scan request for: {url}")

    async def generate_stream():
        try:
            async for data_line in run_full_scan_stream(url):
                yield data_line
        except Exception as e:
            print(f"[WebApp] Error during scan stream: {e}")
            yield f"data: [ERROR] A critical error occurred: {e}\\n\\n"

    return Response(asyncio.run(generate_stream()), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
