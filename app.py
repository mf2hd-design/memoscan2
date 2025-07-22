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

    # This is a synchronous wrapper that correctly runs the async generator.
    def sync_stream_wrapper():
        # Create a new event loop for this background task.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async_gen = run_full_scan_stream(url)

        try:
            while True:
                # Run the async generator until it produces the next item.
                yield loop.run_until_complete(async_gen.__anext__())
        except StopAsyncIteration:
            # The generator is finished.
            pass
        except Exception as e:
            print(f"[WebApp] Error in stream wrapper: {e}")
            yield f"data: [ERROR] A critical error occurred: {e}\\n\\n"
        finally:
            loop.close()
            
    # We now pass the standard, synchronous generator to the Response object.
    return Response(sync_stream_wrapper(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
