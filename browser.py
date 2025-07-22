import os
import json
import base64
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import traceback

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
from selenium.webdriver.common.service import Service as BaseService
from PIL import Image
import io

# Configuration
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)

# Global storage for user sessions
user_sessions: Dict[str, Dict[str, Any]] = {}
browser_sessions: Dict[str, webdriver.Chrome] = {}

def find_chrome_binary():
    """Find Chrome/Chromium binary in common locations"""
    possible_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/opt/google/chrome/chrome",
        "/usr/local/bin/google-chrome",
        "/usr/local/bin/chromium"
    ]
    
    for path in possible_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"Found Chrome binary at: {path}")
            return path
    
    # Check if chrome is in PATH
    import shutil
    chrome_path = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if chrome_path:
        print(f"Found Chrome binary in PATH: {chrome_path}")
        return chrome_path
    
    return None

def find_chromedriver_path():
    """Find the ChromeDriver executable in common locations"""
    possible_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/opt/chromedriver",
        "./chromedriver",
        "chromedriver",
        "/snap/bin/chromium.chromedriver"
    ]
    
    for path in possible_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"Found ChromeDriver at: {path}")
            return path
    
    # Check if chromedriver is in PATH
    import shutil
    chromedriver_path = shutil.which("chromedriver")
    if chromedriver_path:
        print(f"Found ChromeDriver in PATH: {chromedriver_path}")
        return chromedriver_path
    
    return None

class BrowserManager:
    def __init__(self, phone_number: str):
        self.phone_number = phone_number
        self.driver = None
        self.profile_path = f"/tmp/chrome_profile_{phone_number}"
        self.downloads_path = f"./downloads/{phone_number}"
        Path(self.downloads_path).mkdir(parents=True, exist_ok=True)
    
    def start_browser(self) -> bool:
        try:
            # Find Chrome binary
            chrome_binary = find_chrome_binary()
            if not chrome_binary:
                print("Chrome/Chromium browser not found. Please install it first.")
                return False
            
            # Find ChromeDriver path
            chromedriver_path = find_chromedriver_path()
            if not chromedriver_path:
                print("ChromeDriver not found. Please ensure it's installed and in PATH.")
                return False
            
            chrome_options = Options()
            chrome_options.binary_location = chrome_binary
            chrome_options.add_argument(f"--user-data-dir={self.profile_path}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_experimental_option("prefs", {
                "download.default_directory": os.path.abspath(self.downloads_path),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })
            
            # Create service with the found ChromeDriver path
            service = Service(chromedriver_path)
            
            try:
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e1:
                print(f"Failed with service: {e1}")
                return False
            
            self.driver.implicitly_wait(10)
            
            # Remove automation indicators
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print(f"Browser started successfully for {self.phone_number}")
            return True
            
        except Exception as e:
            print(f"Error starting browser: {e}")
            traceback.print_exc()
            return False
    
    def close_browser(self):
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                print(f"Browser closed for {self.phone_number}")
                return True
            except Exception as e:
                print(f"Error closing browser: {e}")
                return False
        return True
    
    def take_screenshot(self) -> str:
        if not self.driver:
            return ""
        try:
            screenshot = self.driver.get_screenshot_as_png()
            return base64.b64encode(screenshot).decode('utf-8')
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return ""
    
    def execute_action(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        if not self.driver:
            return False, "Browser not started"
        
        try:
            action_type = action.get("type", "")
            
            if action_type == "navigate":
                url = action.get("url", "")
                self.driver.get(url)
                time.sleep(3)
                return True, f"Navigated to {url}"
            
            elif action_type == "click":
                x = action.get("x", 0)
                y = action.get("y", 0)
                ActionChains(self.driver).move_by_offset(x, y).click().perform()
                ActionChains(self.driver).reset_actions()
                time.sleep(2)
                return True, f"Clicked at coordinates ({x}, {y})"
            
            elif action_type == "click_element":
                selector = action.get("selector", "")
                try:
                    element = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                    time.sleep(2)
                    return True, f"Clicked element: {selector}"
                except TimeoutException:
                    return False, f"Element not found or not clickable: {selector}"
            
            elif action_type == "type":
                text = action.get("text", "")
                ActionChains(self.driver).send_keys(text).perform()
                time.sleep(1)
                return True, f"Typed: {text}"
            
            elif action_type == "type_in_element":
                selector = action.get("selector", "")
                text = action.get("text", "")
                try:
                    element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    element.clear()
                    element.send_keys(text)
                    time.sleep(1)
                    return True, f"Typed '{text}' in element: {selector}"
                except TimeoutException:
                    return False, f"Element not found: {selector}"
            
            elif action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                if direction == "down":
                    self.driver.execute_script(f"window.scrollBy(0, {amount});")
                elif direction == "up":
                    self.driver.execute_script(f"window.scrollBy(0, -{amount});")
                elif direction == "top":
                    self.driver.execute_script("window.scrollTo(0, 0);")
                elif direction == "bottom":
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                return True, f"Scrolled {direction} by {amount}px"
            
            elif action_type == "key_press":
                key = action.get("key", "")
                try:
                    if hasattr(Keys, key.upper()):
                        ActionChains(self.driver).send_keys(getattr(Keys, key.upper())).perform()
                        time.sleep(1)
                        return True, f"Pressed key: {key}"
                    else:
                        return False, f"Unknown key: {key}"
                except Exception as e:
                    return False, f"Error pressing key: {str(e)}"
            
            elif action_type == "new_tab":
                self.driver.execute_script("window.open('');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                time.sleep(1)
                return True, "Opened new tab"
            
            elif action_type == "close_tab":
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(self.driver.window_handles[-1])
                    time.sleep(1)
                    return True, "Closed current tab"
                else:
                    return False, "Cannot close the last tab"
            
            elif action_type == "switch_tab":
                tab_index = action.get("index", 0)
                if 0 <= tab_index < len(self.driver.window_handles):
                    self.driver.switch_to.window(self.driver.window_handles[tab_index])
                    time.sleep(1)
                    return True, f"Switched to tab {tab_index}"
                else:
                    return False, f"Invalid tab index: {tab_index}"
            
            elif action_type == "wait":
                seconds = action.get("seconds", 1)
                time.sleep(seconds)
                return True, f"Waited {seconds} seconds"
            
            elif action_type == "refresh":
                self.driver.refresh()
                time.sleep(3)
                return True, "Page refreshed"
            
            elif action_type == "back":
                self.driver.back()
                time.sleep(2)
                return True, "Navigated back"
            
            elif action_type == "forward":
                self.driver.forward()
                time.sleep(2)
                return True, "Navigated forward"
            
            else:
                return False, f"Unknown action type: {action_type}"
                
        except Exception as e:
            return False, f"Error executing action: {str(e)}"

def get_system_prompt() -> str:
    return """You are Magic Agent, an AI assistant that can control a web browser and help users with various tasks. You have the following capabilities:

BROWSER COMMANDS:
1. START_BROWSER - Start a new browser session
2. CLOSE_BROWSER - Close the current browser session
3. NAVIGATE:{"url": "https://example.com"} - Navigate to a URL
4. CLICK:{"x": 100, "y": 200} - Click at specific coordinates on screen
5. CLICK_ELEMENT:{"selector": "button#submit"} - Click on a specific element using CSS selector
6. TYPE:{"text": "hello world"} - Type text at current cursor position
7. TYPE_IN_ELEMENT:{"selector": "input[type='email']", "text": "user@example.com"} - Type in a specific element
8. SCROLL:{"direction": "down", "amount": 500} - Scroll the page (direction: up/down/top/bottom, amount in pixels)
9. KEY_PRESS:{"key": "ENTER"} - Press a keyboard key (ENTER, TAB, ESCAPE, etc.)
10. NEW_TAB - Open a new tab
11. CLOSE_TAB - Close current tab
12. SWITCH_TAB:{"index": 0} - Switch to tab by index
13. WAIT:{"seconds": 2} - Wait for specified seconds
14. REFRESH - Refresh the current page
15. BACK - Navigate back in browser history
16. FORWARD - Navigate forward in browser history
17. PAUSE_FOR_USER - Pause browser session to ask user for more information

IMPORTANT RULES:
- Always describe what you're doing before executing commands
- When you receive a screenshot, analyze it carefully before deciding actions
- Use coordinates for clicking when CSS selectors aren't reliable
- Be patient and wait for pages to load
- If something doesn't work, try alternative approaches
- Ask the user for clarification when needed using PAUSE_FOR_USER
- Always close the browser when the task is complete
- Provide clear updates on your progress
- Wait for pages to fully load before taking actions
- Use specific and reliable CSS selectors when possible

When a user asks you to do something that requires browser interaction, start with START_BROWSER and end with CLOSE_BROWSER when done.

Format your commands exactly as shown above. The system will execute them and provide you with screenshots after each action."""

def send_whatsapp_message(phone_number: str, message: str):
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def send_whatsapp_image(phone_number: str, image_base64: str, caption: str = ""):
    try:
        image_data = base64.b64decode(image_base64)
        temp_path = f"/tmp/screenshot_{phone_number}_{int(time.time())}.png"
        
        with open(temp_path, "wb") as f:
            f.write(image_data)
        
        # Upload image first
        upload_url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        
        with open(temp_path, "rb") as f:
            files = {"file": f}
            data = {"messaging_product": "whatsapp", "type": "image"}
            upload_response = requests.post(upload_url, headers=headers, files=files, data=data)
        
        os.remove(temp_path)
        
        if upload_response.status_code == 200:
            media_id = upload_response.json().get("id")
            
            # Send image message
            message_url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
            headers["Content-Type"] = "application/json"
            
            message_data = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "image",
                "image": {"id": media_id, "caption": caption}
            }
            
            response = requests.post(message_url, headers=headers, json=message_data)
            return response.status_code == 200
    
    except Exception as e:
        print(f"Error sending image: {e}")
        return False

def process_ai_response(phone_number: str, ai_response: str) -> str:
    browser_manager = browser_sessions.get(phone_number)
    
    # Extract commands from AI response
    lines = ai_response.split('\n')
    status_message = ""
    
    for line in lines:
        line = line.strip()
        
        if line == "START_BROWSER":
            if phone_number not in browser_sessions:
                browser_manager = BrowserManager(phone_number)
                if browser_manager.start_browser():
                    browser_sessions[phone_number] = browser_manager
                    status_message += "✅ Browser started successfully\n"
                    # Take initial screenshot
                    screenshot = browser_manager.take_screenshot()
                    if screenshot:
                        send_whatsapp_image(phone_number, screenshot, "Browser started")
                else:
                    status_message += "❌ Failed to start browser\n"
            else:
                status_message += "ℹ️ Browser already running\n"
        
        elif line == "CLOSE_BROWSER":
            if phone_number in browser_sessions:
                browser_manager = browser_sessions[phone_number]
                if browser_manager.close_browser():
                    del browser_sessions[phone_number]
                    status_message += "✅ Browser closed successfully\n"
                else:
                    status_message += "❌ Failed to close browser\n"
            else:
                status_message += "ℹ️ No browser session to close\n"
        
        elif line == "PAUSE_FOR_USER":
            status_message += "⏸️ Paused for user input. Please provide more information.\n"
            break
        
        elif line.startswith(("NAVIGATE:", "CLICK:", "CLICK_ELEMENT:", "TYPE:", "TYPE_IN_ELEMENT:", 
                            "SCROLL:", "KEY_PRESS:", "SWITCH_TAB:", "WAIT:")):
            if browser_manager:
                try:
                    command, params_str = line.split(":", 1)
                    params = json.loads(params_str)
                    success, message = browser_manager.execute_action({"type": command.lower(), **params})
                    
                    if success:
                        status_message += f"✅ {message}\n"
                        # Take screenshot after action
                        screenshot = browser_manager.take_screenshot()
                        if screenshot:
                            send_whatsapp_image(phone_number, screenshot, f"Magic Agent: {message}")
                    else:
                        status_message += f"❌ {message}\n"
                except Exception as e:
                    status_message += f"❌ Error parsing command: {str(e)}\n"
            else:
                status_message += "❌ No browser session active\n"
        
        elif line in ["NEW_TAB", "CLOSE_TAB", "REFRESH", "BACK", "FORWARD"]:
            if browser_manager:
                success, message = browser_manager.execute_action({"type": line.lower()})
                if success:
                    status_message += f"✅ {message}\n"
                    screenshot = browser_manager.take_screenshot()
                    if screenshot:
                        send_whatsapp_image(phone_number, screenshot, f"Magic Agent: {message}")
                else:
                    status_message += f"❌ {message}\n"
            else:
                status_message += "❌ No browser session active\n"
    
    return status_message

def get_ai_response(phone_number: str, message: str) -> str:
    try:
        # Get or create user session
        if phone_number not in user_sessions:
            user_sessions[phone_number] = {"chat": None}
        
        # Initialize chat if needed
        if user_sessions[phone_number]["chat"] is None:
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash-exp",
                system_instruction=get_system_prompt()
            )
            user_sessions[phone_number]["chat"] = model.start_chat(history=[])
        
        chat = user_sessions[phone_number]["chat"]
        
        # Prepare message content
        content = [message]
        
        # Add screenshot if browser is active
        if phone_number in browser_sessions:
            browser_manager = browser_sessions[phone_number]
            screenshot = browser_manager.take_screenshot()
            if screenshot:
                content.append({
                    "mime_type": "image/png",
                    "data": screenshot
                })
        
        # Get AI response
        response = chat.send_message(content)
        ai_response = response.text
        
        # Process browser commands
        command_status = process_ai_response(phone_number, ai_response)
        
        # Combine AI response with command status
        if command_status:
            return f"{ai_response}\n\n--- Action Status ---\n{command_status}"
        else:
            return ai_response
            
    except Exception as e:
        print(f"Error getting AI response: {e}")
        traceback.print_exc()
        return f"Sorry, I encountered an error: {str(e)}"

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        
        if data.get('object') == 'whatsapp_business_account':
            entries = data.get('entry', [])
            
            for entry in entries:
                changes = entry.get('changes', [])
                
                for change in changes:
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    
                    for message in messages:
                        phone_number = message.get('from')
                        message_type = message.get('type')
                        
                        if message_type == 'text':
                            text = message.get('text', {}).get('body', '')
                            
                            # Get AI response
                            ai_response = get_ai_response(phone_number, text)
                            
                            # Send response
                            send_whatsapp_message(phone_number, ai_response)
                        
                        else:
                            # Handle non-text messages
                            error_message = "❌ Sorry, I can only process text messages. Please send your request as text."
                            send_whatsapp_message(phone_number, error_message)
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        print(f"Webhook error: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error'}), 500

if __name__ == '__main__':
    print("Starting Magic Agent WhatsApp Bot...")
    print("Browser automation capabilities enabled")
    print("Checking system requirements...")
    
    # Check Chrome binary
    chrome_binary = find_chrome_binary()
    if chrome_binary:
        print(f"✅ Chrome binary found at: {chrome_binary}")
    else:
        print("❌ Chrome/Chromium browser not found!")
        print("Please install Chrome or Chromium:")
        print("For Google Chrome:")
        print("  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -")
        print("  echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' | sudo tee /etc/apt/sources.list.d/google-chrome.list")
        print("  sudo apt update")
        print("  sudo apt install google-chrome-stable")
        print("")
        print("For Chromium (alternative):")
        print("  sudo apt update")
        print("  sudo apt install chromium-browser")
    
    # Check ChromeDriver
    chromedriver_path = find_chromedriver_path()
    if chromedriver_path:
        print(f"✅ ChromeDriver found at: {chromedriver_path}")
    else:
        print("❌ ChromeDriver not found!")
        print("Please install ChromeDriver:")
        print("  sudo apt update")
        print("  sudo apt install chromium-chromedriver")
        print("Or download manually from: https://chromedriver.chromium.org/downloads")
    
    if chrome_binary and chromedriver_path:
        print("🚀 All requirements satisfied! Starting server...")
    else:
        print("⚠️  Missing requirements. Please install them first.")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
