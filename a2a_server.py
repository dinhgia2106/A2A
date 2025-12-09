from flask import Flask, jsonify, request
import time
import uuid
import threading
from game_maker_agent import process_task

app = Flask(__name__)
PORT = 5000

# --- 1. AGENT CARD (/.well-known/agent-card.json) ---
# Client Agent will access this file first to know the capabilities of the Server Agent
AGENT_CARD_DATA = {
    "name": "GameCodeGenerator",
    "version": "1.0",
    "description": "Agent specialized in writing Python game code (Tkinter).",
    "serviceEndpoint": f"http://127.0.0.1:{PORT}",
    "capabilities": ["python_coding", "tkinter_gui"],
    "supported_modalities": ["text"],
    "authRequired": False
}

@app.route('/.well-known/agent-card.json', methods=['GET'])
def get_agent_card():
    """Endpoint to publish Agent Card."""
    return jsonify(AGENT_CARD_DATA)

# --- 2. TASK SUBMISSION SYSTEM ---

# In-memory storage for tasks
# Format: { task_id: { "status": "...", "result": {}, "created_at": ... } }
TASKS = {}

def background_task_runner(task_id, prompt):
    """Run agent in background thread."""
    print(f"[SERVER]: Starting Task {task_id} in background...")
    try:
        # Call actual Agent
        result = process_task(prompt)
        
        # Update result
        TASKS[task_id]["status"] = result["status"] # COMPLETED or FAILED or ERROR
        TASKS[task_id]["result"] = result
        print(f"[SERVER]: Task {task_id} completed with status {result['status']}")
        
    except Exception as e:
        TASKS[task_id]["status"] = "FAILED"
        TASKS[task_id]["result"] = {"error": str(e)}
        print(f"[SERVER]: Task {task_id} failed: {e}")

@app.route('/tasks', methods=['POST'])
def submit_task(): 
    
    """Endpoint to receive and process new Task."""
    
    task_id = str(uuid.uuid4())
    task_request = request.json
    user_prompt = task_request.get("prompt", "")
    
    if not user_prompt:
        return jsonify({"error": "Prompt is required"}), 400

    print(f"\n[SERVER]: Received Task ID: {task_id}")
    print(f"[SERVER]: Request: {user_prompt}")
    
    # Initialize Task status
    TASKS[task_id] = {
        "status": "Running",
        "result": None,
        "created_at": time.time(),
        "prompt": user_prompt
    }
    
    # Run background thread
    thread = threading.Thread(target=background_task_runner, args=(task_id, user_prompt))
    thread.start()
    
    response_data = {
        "task_id": task_id,
        "status": "SUBMITTED",
        "message": "Task is being processed in background."
    }

    return jsonify(response_data), 202

@app.route('/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Check task status."""
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
        
    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"]
    })

if __name__ == '__main__':
    print(f"Starting A2A Server at http://127.0.0.1:{PORT}")
    app.run(port=PORT)
