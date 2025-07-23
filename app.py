import asyncio
import uuid
from quart import Quart, render_template, request, Response, jsonify
from scanner import run_full_scan

app = Quart(__name__)

# A simple in-memory dictionary to store the state of our tasks.
# In a larger application, you would use a database or Redis for this.
tasks = {}

@app.route("/")
async def index():
    return await render_template("index.html")

@app.route("/scan", methods=["POST"])
async def scan():
    """
    This endpoint now starts the scan as a background task and immediately
    returns a unique task_id to the client.
    """
    data = await request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL parameter is missing."}), 400

    task_id = str(uuid.uuid4())
    print(f"[WebApp] Received scan request for: {url}. Assigning task_id: {task_id}")
    
    # Initialize the state for this new task
    tasks[task_id] = {'status': 'pending', 'results': []}
    
    # Start the long-running scan in the background.
    # Quart's app.add_background_task is the correct way to do this.
    app.add_background_task(run_full_scan, tasks, task_id, url)
    
    # Immediately return the task_id to the client.
    return jsonify({"task_id": task_id})

@app.route("/status/<task_id>")
async def status(task_id):
    """
    This is the new Server-Sent Events (SSE) endpoint that streams the
    progress and results of a background task.
    """
    if task_id not in tasks:
        return "Task not found", 404

    async def _generate():
        # Keep track of how many results we've already sent for this task
        sent_results_count = 0
        
        while True:
            # Check if there are new results to send
            if len(tasks[task_id]['results']) > sent_results_count:
                new_results = tasks[task_id]['results'][sent_results_count:]
                for result in new_results:
                    yield result
                sent_results_count = len(tasks[task_id]['results'])

            # If the task is complete, we can stop streaming
            if tasks[task_id]['status'] == 'complete':
                break
            
            # Wait for a short period before checking for new results again
            await asyncio.sleep(1)

    return Response(_generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
