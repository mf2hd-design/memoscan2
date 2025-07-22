from quart import Quart, render_template, request, Response
from scanner import run_full_scan_stream

app = Quart(__name__)

@app.route("/")
async def index():
    return await render_template("index.html")

@app.route("/scan")
async def scan():
    url = request.args.get("url", "").strip()

    # Define an inner async generator function.
    # This is the correct pattern for streaming with Quart.
    async def _generate():
        if not url:
            yield "data: [ERROR] URL parameter is missing.\\n\\n"
            return

        print(f"[WebApp] Received scan request for: {url}")

        # We can now directly loop over our async scanner and yield the results.
        async for data in run_full_scan_stream(url):
            yield data

    # We call _generate() to create the generator object
    # and pass that object to the Response.
    return Response(_generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
