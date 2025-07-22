# Note the new imports from Quart
from quart import Quart, render_template, request, Response, stream_with_context
from scanner import run_full_scan_stream

# We now instantiate a Quart app
app = Quart(__name__)

@app.route("/")
async def index():
    # We can now use async in our route functions
    return await render_template("index.html")

@app.route("/scan")
async def scan():
    url = request.args.get("url", "").strip()
    if not url:
        # We must return an async generator for streaming responses
        async def error_stream():
            yield "data: [ERROR] URL parameter is missing.\\n\\n"
        return Response(error_stream(), mimetype="text/event-stream")

    print(f"[WebApp] Received scan request for: {url}")

    # This is now incredibly simple. Because this function and the scanner are both async,
    # we can just directly return the stream from the scanner. No more wrappers.
    return Response(stream_with_context(run_full_scan_stream(url)), mimetype="text/event-stream")

if __name__ == "__main__":
    # Standard way to run a Quart app for local testing
    app.run(debug=True, host="0.0.0.0", port=10000)
