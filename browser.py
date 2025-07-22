# Save this file as "whatsapp.py" inside your "clicky" folder.

import os
import json
import base64
import time
import threading
import traceback
import shutil
import signal # --- CHANGE ---: Import signal for process management
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- Configuration ---
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
# --- CHANGE ---: Using the officially recommended latest alias for the flash model.
GEMINI_MODEL_NAME = "gemini-2.0-flash"

# --- AI Initialization ---
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# --- Global In-Memory Storage ---
user_sessions: Dict[str, Dict[str, Any]] = {}
browser_managers: Dict[str, 'BrowserManager'] = {}

def find_executable(name: str) -> Optional[str]:
    """Find an executable in common system paths."""
    if path := shutil.which(name):
        print(f"Found {name} in PATH: {path}")
        return path

    possible_paths = [ f"/usr/bin/{name}", f"/usr/local/bin/{name}", f"/snap/bin/{name.replace('google-chrome', 'chromium')}", f"/snap/bin/{name.replace('chromedriver', 'chromium.chromedriver')}"]
    for path in possible_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"Found {name} at: {path}")
            return path
    
    print(f"Warning: Could not find {name} in common paths or system PATH.")
    return None

class BrowserManager:
    """Manages a single Selenium browser instance for a specific user."""
    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.driver: Optional[webdriver.Chrome] = None
        self.profile_path = Path(f"/tmp/chrome_profile_{self.phone_number}")
        self.downloads_path = Path(f"./downloads/{self.phone_number}").resolve()
        self.downloads_path.mkdir(parents=True, exist_ok=True)
        self.service: Optional[Service] = None # --- CHANGE ---: To manage the service process

    # --- CHANGE START ---: Added a robust cleanup method.
    def _cleanup_stale_processes(self):
        """Finds and terminates stale Chrome processes using this profile."""
        print(f"[{self.phone_number}] Running cleanup for profile: {self.profile_path}")
        try:
            # This command finds processes using the specific user-data-dir and kills them.
            # It's a robust way to ensure the profile is free before starting.
            cmd = f"ps aux | grep 'user-data-dir={self.profile_path}' | grep -v grep | awk '{{print $2}}' | xargs -r kill -9"
            os.system(cmd)
            print(f"[{self.phone_number}] Stale process cleanup command executed.")
            # Also, ensure the directory lock file is gone if it exists
            lockfile = self.profile_path / "SingletonLock"
            if lockfile.exists():
                print(f"[{self.phone_number}] Removing stale SingletonLock file.")
                os.remove(lockfile)
        except Exception as e:
            print(f"[{self.phone_number}] Error during stale process cleanup: {e}")
    # --- CHANGE END ---

    def start_browser(self) -> Tuple[bool, str]:
        """Starts a headless Chrome browser instance."""
        if self.driver:
            return True, "Browser is already running."
            
        # --- CHANGE ---: Call cleanup before attempting to start.
        self._cleanup_stale_processes()
        # A small delay to ensure OS has time to release file locks after killing processes
        time.sleep(1)

        try:
            chrome_binary_path = find_executable("google-chrome")
            chromedriver_path = find_executable("chromedriver")

            if not chrome_binary_path:
                return False, "Chrome binary not found. Please install Google Chrome."
            if not chromedriver_path:
                return False, "ChromeDriver not found. Please install it and ensure it's in the PATH."

            options = Options()
            options.binary_location = chrome_binary_path
            options.add_argument(f"--user-data-dir={self.profile_path}")
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,1024")
            options.add_experimental_option("prefs", {
                "download.default_directory": str(self.downloads_path),
                "download.prompt_for_download": False, "download.directory_upgrade": True,
            })
            
            self.service = Service(executable_path=chromedriver_path) # --- CHANGE ---
            self.driver = webdriver.Chrome(service=self.service, options=options)
            print(f"Browser started for {self.phone_number}. Profile: {self.profile_path}")
            return True, "Browser started successfully."
        except WebDriverException as e:
            error_msg = f"Failed to start browser for {self.phone_number}: {e.msg}"
            print(error_msg)
            traceback.print_exc()
            return False, error_msg
        except Exception as e:
            error_msg = f"An unexpected error occurred while starting browser: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            return False, error_msg

    def close_browser(self):
        """Closes the browser and cleans up."""
        if self.driver:
            print(f"[{self.phone_number}] Attempting to close browser...")
            try:
                self.driver.quit()
            except Exception as e:
                print(f"[{self.phone_number}] driver.quit() failed with error: {e}. Will try killing process.")

            # --- CHANGE ---: More robust shutdown by also stopping the service process
            if self.service and self.service.process:
                try:
                    self.service.process.send_signal(signal.SIGTERM)
                    self.service.process.wait(timeout=5)
                except Exception as e:
                    print(f"[{self.phone_number}] Could not terminate service process gracefully: {e}")
                    self.service.process.kill()

            self.driver = None
            self.service = None
            print(f"[{self.phone_number}] Browser session resources released.")
        
        # --- CHANGE ---: Run cleanup after closing to be absolutely sure.
        self._cleanup_stale_processes()


    def take_screenshot(self) -> Optional[str]:
        """Takes a screenshot and returns it as a base64 encoded string."""
        if not self.driver:
            return None
        try:
            png_data = self.driver.get_screenshot_as_png()
            return base64.b64encode(png_data).decode('utf-8')
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None

    def execute_action(self, command: str, params: Dict) -> Tuple[bool, str]:
        """Executes a browser action based on a command and parameters."""
        if not self.driver:
            return False, "Browser is not running. Please use START_BROWSER first."

        try:
            if command == "navigate":
                url = params.get("url", "https://google.com")
                self.driver.get(url)
                time.sleep(3) 
                return True, f"Navigated to {url}"
            
            elif command == "click":
                x, y = params.get("x"), params.get("y")
                element = self.driver.execute_script("return document.elementFromPoint(arguments[0], arguments[1]);", x, y)
                if element:
                    element.click()
                    time.sleep(2)
                    return True, f"Clicked element at ({x}, {y})"
                return False, f"Could not find a clickable element at ({x}, {y})"

            elif command == "click_element":
                selector = params.get("selector")
                element = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                element.click()
                time.sleep(2)
                return True, f"Clicked element with selector '{selector}'"

            elif command == "type":
                text = params.get("text", "")
                element = self.driver.switch_to.active_element
                element.send_keys(text)
                time.sleep(1)
                return True, f"Typed: '{text}'"

            elif command == "type_in_element":
                selector = params.get("selector")
                text = params.get("text", "")
                element = WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                element.clear()
                element.send_keys(text)
                time.sleep(1)
                return True, f"Typed '{text}' in element '{selector}'"

            elif command == "scroll":
                direction = params.get("direction", "down")
                if direction == "down": self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
                elif direction == "up": self.driver.execute_script("window.scrollBy(0, -window.innerHeight);")
                elif direction == "top": self.driver.execute_script("window.scrollTo(0, 0);")
                elif direction == "bottom": self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                return True, f"Scrolled {direction}"

            elif command == "key_press":
                key = params.get("key", "ENTER").upper()
                key_to_press = getattr(Keys, key)
                self.driver.switch_to.active_element.send_keys(key_to_press)
                time.sleep(1)
                return True, f"Pressed key: {key}"

            elif command == "new_tab":
                self.driver.switch_to.new_window('tab')
                time.sleep(1)
                return True, "Opened and switched to new tab"

            elif command == "close_tab":
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    return True, "Closed tab and switched to previous one"
                return False, "Cannot close the last tab"

            elif command == "switch_tab":
                index = params.get("index", 0)
                if 0 <= index < len(self.driver.window_handles):
                    self.driver.switch_to.window(self.driver.window_handles[index])
                    return True, f"Switched to tab at index {index}"
                return False, f"Invalid tab index {index}"
            
            else:
                return False, f"Unknown command: {command}"

        except TimeoutException:
            return False, f"Action failed: Element not found or visible within 10 seconds."
        except Exception as e:
            return False, f"An error occurred during action '{command}': {str(e)}"

# --- The rest of the file (WhatsApp communication, Core AI logic, Flask routes) is unchanged. ---
# --- You can copy-paste the code below this line from the previous response as it's identical. ---

def send_whatsapp_message(phone_number: str, message: str):
    """Sends a text message to a WhatsApp user."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message}}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Sent message to {phone_number}: {message[:80]}...")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")

def send_whatsapp_image(phone_number: str, image_base64: str, caption: str):
    """Uploads and sends an image to a WhatsApp user."""
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    image_data = base64.b64decode(image_base64)
    files = {'file': ('screenshot.png', image_data, 'image/png')}
    data = {'messaging_product': 'whatsapp'}
    try:
        upload_res = requests.post(upload_url, headers=headers, files=files, data=data, timeout=20)
        upload_res.raise_for_status()
        media_id = upload_res.json().get("id")
        if not media_id:
            print("Failed to get media ID from upload response.")
            send_whatsapp_message(phone_number, f"(Could not send screenshot)\n\n{caption}")
            return
        message_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        msg_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "image", "image": {"id": media_id, "caption": caption}}
        send_res = requests.post(message_url, headers=msg_headers, json=payload, timeout=10)
        send_res.raise_for_status()
        print(f"Sent image to {phone_number} with caption: {caption}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp image: {e}")
        send_whatsapp_message(phone_number, f"(Could not send screenshot)\n\n{caption}")

def get_system_prompt():
    return """
You are Magic Agent, a powerful AI assistant that controls a web browser to perform tasks for a user. You operate by issuing commands in a specific JSON-like format.

**Your Goal:** Understand the user's request, break it down into a series of browser actions, and execute them one by one. After each action, you will receive a new screenshot and must decide the next step.

**COMMAND FORMAT:**
You MUST issue commands on new lines, one command at a time, in the format: `COMMAND:{"param": "value"}`.

**Available Commands:**
- `START_BROWSER:{}`: Initializes the browser session. ALWAYS start with this.
- `NAVIGATE:{"url": "https://www.google.com"}`: Opens a specific URL.
- `TYPE_IN_ELEMENT:{"selector": "input[name='q']", "text": "how to use selenium"}`: Types text into an element found by a CSS selector.
- `CLICK_ELEMENT:{"selector": "button#submit"}`: Clicks an element found by a CSS selector. Use precise selectors.
- `SCROLL:{"direction": "down"}`: Scrolls the page. Directions: "up", "down", "top", "bottom".
- `KEY_PRESS:{"key": "ENTER"}`: Simulates a key press on the focused element (e.g., ENTER, TAB, ESCAPE).
- `PAUSE_FOR_USER:{"reason": "I need you to solve this captcha."}`: Stops execution and asks the user for information.
- `CLOSE_BROWSER:{}`: Terminates the browser session. ALWAYS use this when the task is complete.
- `NEW_TAB:{}`: Opens a new browser tab.
- `CLOSE_TAB:{}`: Closes the current tab.
- `SWITCH_TAB:{"index": 0}`: Switches to a tab by its number (0 is the first tab).

**Workflow:**
1. User gives you a task (e.g., "find the weather in London").
2. Your first response must be a plan, followed by the `START_BROWSER:{}` command.
3. The system executes your command and sends you a new screenshot.
4. Analyze the screenshot. Issue the next command (e.g., `NAVIGATE:{"url": "https://www.google.com"}`).
5. The system executes it and sends you another screenshot.
6. Analyze the new screenshot. Issue the next command (e.g., `TYPE_IN_ELEMENT:{"selector": "textarea[name=q]", "text": "weather in london"}`).
7. Continue this loop of `Analyze Screenshot -> Issue Command` until the task is done.
8. If you have the answer, state it clearly to the user.
9. Finish the session with the `CLOSE_BROWSER:{}` command.

**IMPORTANT RULES:**
- **ONE COMMAND AT A TIME.** Wait for the next screenshot before issuing a new command.
- **BE DESCRIPTIVE.** Briefly explain what action you are taking before the command. E.g., "Okay, I will now navigate to Google.\nNAVIGATE:{\"url\": \"https://www.google.com\"}"
- **USE CSS SELECTORS.** Be as specific as possible (e.g., `input[aria-label='Search']` is better than `input`).
- **THINK STEP-BY-STEP.** Do not rush. If a page is loading, wait for the next screenshot.
- **TASK COMPLETE.** When you have found the information or completed the action, clearly state the result to the user, then issue `CLOSE_BROWSER:{}`.
"""

def get_or_create_session(phone_number: str):
    """Manages user sessions for chat history and browser instances."""
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        model = genai.GenerativeModel(model_name=GEMINI_MODEL_NAME, system_instruction=get_system_prompt())
        user_sessions[phone_number] = {"chat": model.start_chat(history=[])}
        browser_managers[phone_number] = BrowserManager(phone_number)
    return user_sessions[phone_number], browser_managers[phone_number]

def process_ai_command(phone_number: str, ai_response: str) -> str:
    """Parses and executes a single command from the AI's response."""
    session, browser_manager = get_or_create_session(phone_number)
    command_line = None
    for line in ai_response.splitlines():
        if ':' in line and '{' in line and '}' in line:
            command_line = line.strip()
            break
    if not command_line:
        return ai_response

    try:
        command, params_str = command_line.split(":", 1)
        command = command.strip().lower()
        params = json.loads(params_str)
        user_facing_response = ai_response.split(command_line)[0].strip()
        if user_facing_response:
             send_whatsapp_message(phone_number, user_facing_response)
        success = False
        message = ""

        if command == "start_browser": success, message = browser_manager.start_browser()
        elif command == "close_browser":
            browser_manager.close_browser()
            success, message = True, "Browser session closed."
            if phone_number in browser_managers: del browser_managers[phone_number]
            if phone_number in user_sessions: del user_sessions[phone_number]
        elif command == "pause_for_user":
            reason = params.get('reason', 'I need more information.')
            success, message = True, f"⏸️ Paused. {reason}"
        else:
            success, message = browser_manager.execute_action(command, params)

        if success:
            action_status = f"✅ Action '{command}' succeeded: {message}"
            print(f"[{phone_number}] {action_status}")
            screenshot_b64 = browser_manager.take_screenshot()
            if screenshot_b64:
                send_whatsapp_image(phone_number, screenshot_b64, caption=action_status)
            else:
                send_whatsapp_message(phone_number, action_status)
            return f"Action successful. Here is the new screen. What is the next step?"
        else:
            action_status = f"❌ Action '{command}' failed: {message}"
            print(f"[{phone_number}] {action_status}")
            send_whatsapp_message(phone_number, action_status)
            return f"The last action failed. Reason: {message}. Please analyze the screen and try a different approach or command."

    except (ValueError, json.JSONDecodeError) as e:
        print(f"Invalid command format from AI: {command_line}. Error: {e}")
        return ai_response
    except Exception as e:
        print(f"Error processing command: {e}")
        traceback.print_exc()
        return f"An internal error occurred: {str(e)}"

def handle_user_message(phone_number: str, user_message: str):
    """Main logic to get AI response and trigger the command loop."""
    session, browser_manager = get_or_create_session(phone_number)
    chat = session["chat"]
    content_for_ai = [user_message]
    if browser_manager and browser_manager.driver:
        screenshot_b64 = browser_manager.take_screenshot()
        if screenshot_b64:
            image_part = {"mime_type": "image/png", "data": base64.b64decode(screenshot_b64)}
            content_for_ai.append(image_part)
        else:
            content_for_ai.append(" (Could not retrieve a screenshot)")
    try:
        ai_response = chat.send_message(content_for_ai).text
        feedback_for_ai = process_ai_command(phone_number, ai_response)
        if browser_manager.driver and "paused" not in feedback_for_ai.lower():
            handle_user_message(phone_number, feedback_for_ai)
    except Exception as e:
        print(f"Error in AI interaction loop: {e}")
        traceback.print_exc()
        send_whatsapp_message(phone_number, f"Sorry, an error occurred with the AI model: {str(e)}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return 'Forbidden', 403
    data = request.json
    try:
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    for msg in messages:
                        phone_number = msg.get('from')
                        if msg.get('type') == 'text':
                            user_text = msg['text']['body']
                            print(f"Received from {phone_number}: {user_text}")
                            threading.Thread(target=handle_user_message, args=(phone_number, user_text)).start()
                        else:
                            send_whatsapp_message(phone_number, "I can only understand text messages right now.")
    except Exception as e:
        print(f"Error processing webhook: {e}")
        traceback.print_exc()
    return 'OK', 200

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Starting ---")
    print("Checking system requirements...")
    if not find_executable("google-chrome"): print("❌ CRITICAL: 'google-chrome' not found. Please install it.")
    if not find_executable("chromedriver"): print("❌ CRITICAL: 'chromedriver' not found. Please install it.")
    print("Starting Flask server on port 5000...")
    app.run(host='0.0.0.0', port=5000, threaded=True)
