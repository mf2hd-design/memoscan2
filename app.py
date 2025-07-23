import asyncio
import uuid
from quart import Quart, render_template, request, Response, jsonify

app = Quart(__name__)

# A simple in-memory dictionary to store the state of our tasks.
tasks = {}

@app.route("/")
async def index():
    return await render_template("index.html")

@app.route("/scan", methods=["POST"])
async def scan():
    """
    Starts the scan as a background task and immediately returns a task_id.
    """
    data = await request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL parameter is missing."}), 400

    task_id = str(uuid.uuid4())
    print(f"[WebApp] Received scan request for: {url}. Assigning task_id: {task_id}")
    
    tasks[task_id] = {'status': 'pending', 'results': []}
    
    # Correctly import and run the scanner function in the background
    from scanner import run_full_scan
    app.add_background_task(run_full_scan, tasks, task_id, url)
    
    return jsonify({"task_id": task_id})

@app.route("/status/<task_id>")
async def status(task_id):
    """
    This is the SSE endpoint that streams the progress of a background task,
    now with a robust heartbeat to keep the connection alive.
    """
    if task_id not in tasks:
        return "Task not found", 404

    async def _generate():
        sent_results_count = 0
        
        while True:
            # Check if the task has completed
            if tasks[task_id]['status'] == 'complete':
                # Send any final results that might have arrived
                if len(tasks[task_id]['results']) > sent_results_count:
                    new_results = tasks[task_id]['results'][sent_results_count:]
                    for result in new_results:
                        yield result
                break # Exit the loop

            # Check for new results to send
            if len(tasks[task_id]['results']) > sent_results_count:
                new_results = tasks[task_id]['results'][sent_results_count:]
                for result in new_results:
                    yield result
                sent_results_count = len(tasks[task_id]['results'])
            else:
                # If there are no new results, send a heartbeat to keep the connection alive.
                print(f"[Heartbeat] Sending heartbeat for task {task_id}")
                yield "event: heartbeat\\ndata: {}\\n\\n"
            
            # Wait for a few seconds before the next check/heartbeat
            await asyncio.sleep(5)

    headers = {
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache",
    }
    return Response(_generate(), mimetype="text/event-stream", headers=headers)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
