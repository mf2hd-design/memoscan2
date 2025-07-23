import asyncio
from quart import Quart, render_template, request, Response
from scanner import run_full_scan

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
        
        # --- THIS IS THE NEW LINE ---
        # Immediately send a user-friendly confirmation message to the client.
        yield "data: [STATUS] Request received. Your brand analysis is starting now. This can take up to 90 seconds, so we appreciate your patience.\\n\\n"
        
        # Start the long-running analysis in the background
        analysis_task = asyncio.create_task(run_full_scan(url))

        # This is the heartbeat loop. It runs while the analysis is working.
        while not analysis_task.done():
            try:
                # Wait for the task to finish, but with a timeout
                await asyncio.wait_for(asyncio.shield(analysis_task), timeout=10.0)
            except asyncio.TimeoutError:
                # If we time out, it means the task is still running.
                # Send a heartbeat to keep the connection alive.
                print("[HEARTBEAT] Sending heartbeat...")
                yield "event: heartbeat\\ndata: {}\\n\\n"

        # The task is done. Get the results and stream them back.
        results = analysis_task.result()
        for result_line in results:
            yield result_line

    return Response(_generate(), mimetype="text-event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
