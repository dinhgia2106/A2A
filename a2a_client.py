import requests
import json
import time

SERVER_URL = "http://127.0.0.1:5000"

def discover_and_submit_task(prompt):
    """
    Standard process: Discover Agent Card -> Submit Task.
    """
    
    # --- 1. DISCOVERY ---
    agent_card_url = f"{SERVER_URL}/.well-known/agent-card.json"
    print(f"[CLIENT]: Finding Agent Card at: {agent_card_url}")
    
    try:
        response = requests.get(agent_card_url)
        response.raise_for_status() # Raise error if status code is not 2xx
        agent_card = response.json()
        
        print(f"[CLIENT]: Found Agent: {agent_card['name']} (Version: {agent_card['version']})")
        
    except requests.exceptions.RequestException as e:
        print(f"[CLIENT]: Error discovering Agent Card: {e}")
        return

    # --- 2. CREATE STANDARD TASK ---
    # Task is a standardized unit of work
    task_payload = {
        "prompt": prompt,
        "client_metadata": {
            "source_id": "client_app_x",
            "priority": "high"
        },
        "artifacts_requested": ["text", "code"]
    }
    
    # --- 3. SUBMIT TASK ---
    task_endpoint = f"{SERVER_URL}/tasks"
    print(f"[CLIENT]: Sending Task to: {task_endpoint}")
    
    try:
        response = requests.post(
            task_endpoint, 
            json=task_payload,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        
        task_status = response.json()
        
        # A2A Server must return HTTP 202 (Accepted) or 201 (Created)
        print(f"[CLIENT]: Task accepted ({response.status_code}):")
        print(f"  - Task ID: {task_status['task_id']}")
        print(f"  - Status: {task_status['status']}")
        print(f"  - Message: {task_status['message']}")
        
    except requests.exceptions.RequestException as e:
        print(f"[CLIENT]: Error submitting Task: {e}")
        return

    # --- 4. POLLING STATUS (Wait for result) ---
    task_id = task_status['task_id']
    poll_task_status(task_id)

def poll_task_status(task_id):
    """Continuously poll Server to see if Task is finished."""
    status_url = f"{SERVER_URL}/tasks/{task_id}"
    print(f"[CLIENT]: Starting to monitor status for Task {task_id}...")
    
    while True:
        try:
            response = requests.get(status_url)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                
                if status in ["COMPLETED", "FAILED", "ERROR"]:
                    print(f"\n[CLIENT]: Task finished! Status: {status}")
                    process_result(data.get("result"))
                    break
                else:
                    # Still running (Running / SUBMITTED)
                    print(f"[CLIENT]: Current status: {status}. Waiting 5 seconds...", end='\r')
                    time.sleep(5)
            else:
                print(f"[CLIENT]: Error checking status: {response.status_code}")
                time.sleep(5)
                
        except Exception as e:
            print(f"[CLIENT]: Polling connection error: {e}")
            break

def process_result(result):
    if not result:
        print("[CLIENT]: No result returned.")
        return
        
    print("\n" + "="*40)
    print("RESULT FROM AGENT SERVER")
    print("="*40)
    
    if result.get("status") == "COMPLETED":
        code = result.get("code")
        if code:
            filename = "generated_game_result.py"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"[CLIENT]: Game code saved to file: {filename}")
        
        screenshot = result.get("screenshot_path")
        if screenshot:
            print(f"[CLIENT]: Screenshot captured by server: {screenshot}")
            
        print("\n[CLIENT]: You can run the game using command: python generated_game_result.py")
    else:
        print(f"[CLIENT]: Task failed. Message: {result.get('message')}")
        if result.get('logs'):
            print("Last logs:")
            for log in result['logs'][-5:]:
                print(log.strip())

if __name__ == '__main__':
    user_request = "Write a simple snake game using Pygame library."
    discover_and_submit_task(user_request)
