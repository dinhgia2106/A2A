import os
import re
import time
import json
import subprocess
import sys
import threading
import pyautogui
from PIL import Image
import google.generativeai as genai
from colorama import Fore, Style
from dotenv import load_dotenv

# --- API CONFIGURATION ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
# Use model supporting both text and images
MODEL_NAME = 'gemini-2.5-flash' 

# --- SYSTEM SUPPORT FUNCTIONS (EXECUTION & SCREENSHOT) ---
TEMP_CODE_FILE = "temp_game.py"
TEMP_SCREENSHOT_FILE = "temp_screenshot.png"

def execute_and_capture_screenshot(code_content):
    """
    Save code to temp file, run it in a separate process,
    wait a few seconds, capture screenshot, then kill process.
    """
    print(f"{Fore.YELLOW}[System]: Preparing execution environment...{Style.RESET_ALL}")
    
    # 1. Save code to file
    with open(TEMP_CODE_FILE, "w", encoding="utf-8") as f:
        f.write(code_content)
    
    execution_error = None
    
    # 2. Run code in subprocess
    try:
        # Use sys.executable to ensure current python environment is used
        process = subprocess.Popen(
            [sys.executable, TEMP_CODE_FILE],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print(f"{Fore.YELLOW}[System]: Code running. Waiting 1 second for interface load...{Style.RESET_ALL}")
        time.sleep(1) 
        
        # Force focus window (macOS fix)
        if sys.platform == "darwin":
            try:
                # AppleScript to activate window of the process
                cmd = f'tell application "System Events" to set frontmost of the first process whose unix id is {process.pid} to true'
                subprocess.run(["osascript", "-e", cmd], capture_output=True)
                print(f"{Fore.YELLOW}[System]: Sent Active Window command (macOS)...{Style.RESET_ALL}")
                time.sleep(1) # Wait for window transition
            except Exception as e:
                print(f"{Fore.RED}[System]: Window focus error: {e}{Style.RESET_ALL}")

        # Simulate key press to start game (if required)
        print(f"{Fore.YELLOW}[System]: Sending Enter/Space to start game...{Style.RESET_ALL}")
        try:
            # Press both space and enter to cover common cases
            pyautogui.press(['space', 'enter'])
        except Exception:
            pass
            
        print(f"{Fore.YELLOW}[System]: Waiting 2 seconds for gameplay...{Style.RESET_ALL}")
        time.sleep(2)
        
        # Check if process crashed immediately
        if process.poll() is not None:
             stdout, stderr = process.communicate()
             execution_error = f"Program crashed immediately on startup:\nStdout: {stdout}\nStderr: {stderr}"
        else:
            # 3. Capture FULL screenshot
            screenshot = pyautogui.screenshot()
            screenshot.save(TEMP_SCREENSHOT_FILE)
            print(f"{Fore.YELLOW}[System]: Screenshot saved (Full Screen).{Style.RESET_ALL}")
            
            # 4. Kill process
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            print(f"{Fore.YELLOW}[System]: Game program closed.{Style.RESET_ALL}")

    except Exception as e:
        execution_error = f"System error trying to run code: {str(e)}"
        if 'process' in locals() and process.poll() is None:
             process.kill()

    return execution_error, TEMP_SCREENSHOT_FILE

# --- ENHANCED AGENT DEFINITIONS ---
class Agent:
    def __init__(self, name, system_instruction):
        self.name = name
        self.model = genai.GenerativeModel(
            MODEL_NAME, 
            system_instruction=system_instruction
        )
        self.chat_session = self.model.start_chat(history=[])

    def reply(self, content_parts):
        # content_parts can be a text string OR a list containing [text, image]
        response = self.chat_session.send_message(content_parts)
        return response.text

# 1. Coder Agent
coder = Agent(
    name="Coder",
    system_instruction="""You are a Senior Python Dev specializing in GUI (tkinter, curses). 
    Task: Write Python code to solve the problem. 
    Important requirements: 
    1. Code must be runnable, with a main loop (e.g., window.mainloop() in tkinter).
    2. ONLY RETURN RAW CODE INSIDE A ```python ... ``` BLOCK. Do not explain anything else."""
)

# 2. Reviewer Agent (Code Quality)
reviewer = Agent(
    name="Reviewer",
    system_instruction="You are a QA Engineer specialized in code. Task: Review Python code. Check for logic errors, potential crashes, security issues. If code is good, reply 'APPROVED'. If not, point out specific errors in the code."
)

# 3. Designer Agent (Visual Quality - NEW)
designer = Agent(
    name="Designer",
    system_instruction="You are a UI/UX Designer. Task: Look at the game interface screenshot and evaluate. If the interface is beautiful and intuitive, reply 'APPROVED'. If it looks bad or hard to see, provide specific feedback for the Coder to improve the interface."
)

# --- SUPERVISOR NODE (ENHANCED) ---
def supervisor_node(history_context, latest_code=None, execution_status=None, reviewer_feedback=None, designer_feedback=None):
    system_instruction = """
    You are a Software Project Manager. You have staff: ['Coder', 'Reviewer', 'Designer'].
    You have an additional execution system (System Executor) to run code.

    WORKFLOW:
    
    STATE 1: No code yet (Start or after FINISHing old job)
    -> Assign 'Coder' to write code based on user request.
    
    STATE 2: Coder just returned Code.
    -> Assign 'EXECUTE' (REQUIRED: Must run new code to check and take new screenshot).
    
    STATE 3: Execution System returned result.
    - If 'EXECUTION_ERROR' (Code failed to run): -> Re-assign 'Coder' with error info to fix.
    - If 'EXECUTION_SUCCESS' (Ran and screenshot taken): -> Assign simultaneously to 'Reviewer' (check code) and 'Designer' (check image).
      (At this step, you need to order checks from both. Prioritize assigning Reviewer first in output json).

    STATE 4: Feedback received from Reviewer and Designer.
    - If both Reviewer and Designer 'APPROVED' -> Reply 'FINISH'.
    - If anyone NOT APPROVED -> Summarize errors and re-assign 'Coder' to fix.
    (NOTE: After Coder fixes, process returns to STATE 2 -> MUST 'EXECUTE' again).

    OUTPUT JSON FORMAT: {"next_agent": "Agent_Name_Or_EXECUTE_Or_FINISH", "instruction": "Detailed instruction for that agent based on current situation"}
    """
    
    model = genai.GenerativeModel(
        MODEL_NAME, 
        system_instruction=system_instruction,
        generation_config={"response_mime_type": "application/json"}
    )
    
    # Create prompt summarizing complex situation
    status_prompt = f"Project Status:\n- Original Context: {history_context}\n"
    if latest_code: status_prompt += "- Have latest Code from Coder (not yet tested).\n" if execution_status is None else "- Have Code from Coder.\n"
    if execution_status == "ERROR": status_prompt += f"- Execution Status: ERROR (EXECUTION_ERROR).\n"
    if execution_status == "SUCCESS": status_prompt += f"- Execution Status: SUCCESS (EXECUTION_SUCCESS), screenshot available.\n"
    if reviewer_feedback: status_prompt += f"- Reviewer Feedback: {reviewer_feedback}\n"
    if designer_feedback: status_prompt += f"- Designer Feedback: {designer_feedback}\n"
    
    status_prompt += "\nWhat is the verified next step?" 

    
    response = model.generate_content(status_prompt)
    return json.loads(response.text)

# --- MAIN FUNCTION FOR SERVER ---
def process_task(user_prompt):
    """
    Main processing function for A2A Server.
    Returns dict: {status, message, code, screenshot_path, logs}
    """
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)

    log(f"{Fore.GREEN}User Request:{Style.RESET_ALL} {user_prompt}\n")
    
    # State variables
    current_context = user_prompt
    latest_code = None
    execution_status = None 
    latest_screenshot_path = None
    reviewer_feedback = None
    designer_feedback = None

    max_steps = 12 
    final_status = "FAILED"
    final_message = "Agent reached max steps without finishing."
    
    for i in range(max_steps):
        log(f"\n{Fore.WHITE}{'='*20} Step {i+1} {'='*20}{Style.RESET_ALL}")
        
        # 1. Supervisor decision
        try:
            decision = supervisor_node(
                current_context, latest_code, execution_status, reviewer_feedback, designer_feedback
            )
            next_action = decision.get("next_agent")
            instruction = decision.get("instruction")
        except Exception as e:
            log(f"{Fore.RED}Supervisor Error: {e}{Style.RESET_ALL}")
            return {
                "status": "ERROR",
                "message": f"Supervisor crashed: {e}",
                "code": latest_code,
                "screenshot_path": latest_screenshot_path,
                "logs": logs
            }
        
        log(f"{Fore.MAGENTA}--- Supervisor: Decision -> {next_action} ---{Style.RESET_ALL}")
        log(f"{Fore.MAGENTA}Note: {instruction}{Style.RESET_ALL}")
        
        # --- HANDLE ACTIONS ---
        
        if next_action == "FINISH":
            log(f"\n{Fore.GREEN}🎉 PROCESS COMPLETED! Product approved.{Style.RESET_ALL}")
            final_status = "COMPLETED"
            final_message = "Task completed successfully."
            break

        elif next_action == "EXECUTE":
            if not latest_code:
                log(f"{Fore.RED}[System Error]: Supervisor requested execution but no code available!{Style.RESET_ALL}")
                break
                
            error_msg, screenshot_path = execute_and_capture_screenshot(latest_code)
            
            if error_msg:
                execution_status = "ERROR"
                current_context = f"Error running code:\n{error_msg}"
                reviewer_feedback = None 
                designer_feedback = None
                log(f"{Fore.RED}[Execution]: Code execution error.{Style.RESET_ALL}")
            else:
                execution_status = "SUCCESS"
                latest_screenshot_path = screenshot_path
                current_context = "Code execution successful, screenshot captured."
                reviewer_feedback = None 
                designer_feedback = None
                log(f"{Fore.GREEN}[Execution]: Success. Image: {screenshot_path}{Style.RESET_ALL}")

        elif next_action == "Coder":
            prompt_parts = [instruction]
            if execution_status == "ERROR":
                 prompt_parts.append(f"\nPrevious Runtime Error Info: {current_context}")
            if reviewer_feedback and reviewer_feedback != "APPROVED":
                 prompt_parts.append(f"\nFeedback from Reviewer: {reviewer_feedback}")
            if designer_feedback and designer_feedback != "APPROVED":
                 prompt_parts.append(f"\nFeedback from Designer (interface): {designer_feedback}")

            try:
                response_text = coder.reply("\n".join(prompt_parts))
                match = re.search(r'```python(.*?)```', response_text, re.DOTALL)
                if match:
                    latest_code = match.group(1).strip()
                    log(f"{Fore.CYAN}[Coder]: Submitted new code.{Style.RESET_ALL}")
                    execution_status = None
                    reviewer_feedback = None
                    designer_feedback = None
                else:
                    log(f"{Fore.RED}[Coder Error]: Invalid code format.{Style.RESET_ALL}")
                    current_context = "Coder did not return code in correct format ```python ... ```."
            except Exception as e:
                log(f"{Fore.RED}[Coder Error]: {e}{Style.RESET_ALL}")

        elif next_action == "Reviewer":
            if not latest_code:
                 log(f"{Fore.RED}[System Error]: No code to review.{Style.RESET_ALL}")
                 continue
            response_text = reviewer.reply(f"{instruction}\nHere is the code to review:\n```python\n{latest_code}\n```")
            reviewer_feedback = response_text
            log(f"{Fore.BLUE}[Reviewer]: {reviewer_feedback}{Style.RESET_ALL}")

        elif next_action == "Designer":
            if not latest_screenshot_path or not os.path.exists(latest_screenshot_path):
                 log(f"{Fore.RED}[System Error]: Image not found for Designer.{Style.RESET_ALL}")
                 designer_feedback = "No image available for evaluation."
                 continue
            
            img = Image.open(latest_screenshot_path)
            response_text = designer.reply([instruction, img])
            designer_feedback = response_text
            log(f"{Fore.YELLOW}[Designer]: {designer_feedback}{Style.RESET_ALL}")

    return {
        "status": final_status,
        "message": final_message,
        "code": latest_code,
        "screenshot_path": latest_screenshot_path,
        "logs": logs
    }

if __name__ == "__main__":
    user_request = "Write a classic Tetris game in Python using Tkinter library. Require clear interface, score display, and game over."
    result = process_task(user_request)
    print(f"RESULT: {result['status']}")