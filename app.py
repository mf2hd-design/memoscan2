from quart import Quart, render_template, request, Response
from scanner import run_full_scan_stream

app = Quart(__name__)

@app.route("/")
async def index():
    return await render_template("index.html")

@app.route("/scan")
async def scan():
    url = request.args.get("url", "").strip()

    async def _generate():
        if not url:
            yield "data: [ERROR] URL parameter is missing.\\n\\n"
            return

        print(f"[WebApp] Received scan request for: {url}")
        # Directly iterate over the true async generator from the scanner
        async for data in run_full_scan_stream(url):
            yield data

    return Response(_generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
