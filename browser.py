import os
import json
import base64
import time
import threading
from datetime import datetime
from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
import uuid
from PIL import Image
import io

# Configuration
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)

# Create necessary directories
os.makedirs("user_downloads", exist_ok=True)
os.makedirs("chrome_profiles", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

app = Flask(__name__)

# Global storage for user sessions
user_sessions = {}
browser_sessions = {}

class BrowserController:
    def __init__(self, phone_number):
        self.phone_number = phone_number
        self.driver = None
        self.profile_path = f"chrome_profiles/{phone_number}"
        self.download_path = f"user_downloads/{phone_number}"
        os.makedirs(self.download_path, exist_ok=True)
        
    def start_browser(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument(f"--user-data-dir={self.profile_path}")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_experimental_option("prefs", {
                "download.default_directory": os.path.abspath(self.download_path),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })
            
            service = Service("chromedriver")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            return True
        except Exception as e:
            print(f"Error starting browser: {e}")
            return False
    
    def take_screenshot(self):
        try:
            screenshot_path = f"screenshots/{self.phone_number}_{int(time.time())}.png"
            self.driver.save_screenshot(screenshot_path)
            
            # Convert to base64 for AI
            with open(screenshot_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            
            # Clean up screenshot file
            os.remove(screenshot_path)
            return encoded_string
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            return None
    
    def click(self, x, y):
        try:
            action = ActionChains(self.driver)
            action.move_by_offset(x, y).click().perform()
            action.reset_actions()
            return True
        except Exception as e:
            print(f"Error clicking: {e}")
            return False
    
    def scroll(self, direction, amount=3):
        try:
            if direction.lower() == "down":
                self.driver.execute_script(f"window.scrollBy(0, {amount * 100});")
            elif direction.lower() == "up":
                self.driver.execute_script(f"window.scrollBy(0, -{amount * 100});")
            return True
        except Exception as e:
            print(f"Error scrolling: {e}")
            return False
    
    def type_text(self, text):
        try:
            action = ActionChains(self.driver)
            action.send_keys(text).perform()
            return True
        except Exception as e:
            print(f"Error typing: {e}")
            return False
    
    def press_key(self, key):
        try:
            action = ActionChains(self.driver)
            if key.upper() == "ENTER":
                action.send_keys(Keys.RETURN).perform()
            elif key.upper() == "TAB":
                action.send_keys(Keys.TAB).perform()
            elif key.upper() == "ESC":
                action.send_keys(Keys.ESCAPE).perform()
            elif key.upper() == "CTRL+T":
                action.key_down(Keys.CONTROL).send_keys("t").key_up(Keys.CONTROL).perform()
            elif key.upper() == "CTRL+W":
                action.key_down(Keys.CONTROL).send_keys("w").key_up(Keys.CONTROL).perform()
            return True
        except Exception as e:
            print(f"Error pressing key: {e}")
            return False
    
    def navigate_to(self, url):
        try:
            self.driver.get(url)
            return True
        except Exception as e:
            print(f"Error navigating: {e}")
            return False
    
    def close_browser(self):
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
            return True
        except Exception as e:
            print(f"Error closing browser: {e}")
            return False

def get_ai_response(message, phone_number, screenshot_base64=None):
    try:
        # Initialize chat session if not exists
        if phone_number not in user_sessions:
            model = genai.GenerativeModel("gemini-2.0-flash")
            chat = model.start_chat(history=[])
            user_sessions[phone_number] = chat
        
        chat = user_sessions[phone_number]
        
        # System prompt for browser automation
        system_prompt = """You are Magic Agent, an AI assistant with browser automation capabilities. You can control a Chrome browser through specific commands.

AVAILABLE COMMANDS (use these exact formats):
- START_BROWSER: Start Chrome browser
- CLOSE_BROWSER: Close Chrome browser  
- CLICK(x,y): Click at coordinates x,y
- SCROLL(direction,amount): Scroll up/down (direction: up/down, amount: number)
- TYPE(text): Type text
- KEY(key): Press key (ENTER, TAB, ESC, CTRL+T, CTRL+W)
- NAVIGATE(url): Go to URL
- SCREENSHOT: Take screenshot
- ASK_USER(question): Ask user for more information

IMPORTANT RULES:
1. Always use EXACT command format in your response
2. You can see screenshots when provided
3. Coordinates are in pixels from top-left (0,0)
4. When clicking, be precise with coordinates
5. Always describe what you're doing to the user
6. Take screenshots frequently to see results
7. If you need user input, use ASK_USER command
8. Be helpful and explain your actions

Current capabilities:
- Browse any website
- Click elements, fill forms
- Download files
- Open/close tabs
- Scroll pages
- Navigate between pages

Start conversations normally. Only use browser commands when user requests web browsing tasks."""

        # Prepare message for AI
        if screenshot_base64:
            # Send message with screenshot
            image_data = base64.b64decode(screenshot_base64)
            image = Image.open(io.BytesIO(image_data))
            
            response = chat.send_message([
                system_prompt + "\n\nUser message: " + message + "\n\nScreenshot provided above. Analyze and respond with appropriate action.",
                image
            ])
        else:
            # Send text only
            response = chat.send_message(system_prompt + "\n\nUser message: " + message)
        
        return response.text
    except Exception as e:
        print(f"Error getting AI response: {e}")
        return "Sorry, I encountered an error processing your request."

def execute_browser_command(command, phone_number):
    try:
        if phone_number not in browser_sessions:
            return "Browser not started. Please start browser first."
        
        browser = browser_sessions[phone_number]
        
        if command.startswith("CLICK("):
            coords = command[6:-1].split(",")
            x, y = int(coords[0]), int(coords[1])
            if browser.click(x, y):
                return f"Clicked at ({x}, {y})"
            else:
                return "Failed to click"
        
        elif command.startswith("SCROLL("):
            params = command[7:-1].split(",")
            direction = params[0]
            amount = int(params[1]) if len(params) > 1 else 3
            if browser.scroll(direction, amount):
                return f"Scrolled {direction} by {amount}"
            else:
                return "Failed to scroll"
        
        elif command.startswith("TYPE("):
            text = command[5:-1]
            if browser.type_text(text):
                return f"Typed: {text}"
            else:
                return "Failed to type"
        
        elif command.startswith("KEY("):
            key = command[4:-1]
            if browser.press_key(key):
                return f"Pressed key: {key}"
            else:
                return "Failed to press key"
        
        elif command.startswith("NAVIGATE("):
            url = command[9:-1]
            if browser.navigate_to(url):
                return f"Navigated to: {url}"
            else:
                return "Failed to navigate"
        
        elif command == "SCREENSHOT":
            screenshot = browser.take_screenshot()
            if screenshot:
                return "SCREENSHOT_TAKEN:" + screenshot
            else:
                return "Failed to take screenshot"
        
        else:
            return "Unknown command"
    
    except Exception as e:
        print(f"Error executing command: {e}")
        return f"Error executing command: {e}"

def send_whatsapp_message(phone_number, message):
    try:
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
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def send_whatsapp_image(phone_number, image_base64, caption=""):
    try:
        # Save image temporarily
        image_data = base64.b64decode(image_base64)
        temp_filename = f"temp_screenshot_{phone_number}_{int(time.time())}.png"
        with open(temp_filename, "wb") as f:
            f.write(image_data)
        
        # Upload image to WhatsApp
        upload_url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        
        with open(temp_filename, "rb") as f:
            files = {"file": f}
            data = {"type": "image/png", "messaging_product": "whatsapp"}
            upload_response = requests.post(upload_url, headers=headers, files=files, data=data)
        
        if upload_response.status_code == 200:
            media_id = upload_response.json()["id"]
            
            # Send image message
            send_url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
            headers["Content-Type"] = "application/json"
            message_data = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "image",
                "image": {"id": media_id, "caption": caption}
            }
            
            response = requests.post(send_url, headers=headers, json=message_data)
            success = response.status_code == 200
        else:
            success = False
        
        # Clean up temp file
        os.remove(temp_filename)
        return success
        
    except Exception as e:
        print(f"Error sending image: {e}")
        return False

def process_ai_response(ai_response, phone_number):
    lines = ai_response.split('\n')
    commands_executed = []
    user_message = ""
    screenshot_base64 = None
    
    for line in lines:
        line = line.strip()
        
        # Check for browser commands
        if line == "START_BROWSER":
            if phone_number not in browser_sessions:
                browser_sessions[phone_number] = BrowserController(phone_number)
            
            if browser_sessions[phone_number].start_browser():
                commands_executed.append("✅ Browser started successfully")
                send_whatsapp_message(phone_number, "🌐 Magic Agent started Chrome browser")
            else:
                commands_executed.append("❌ Failed to start browser")
                send_whatsapp_message(phone_number, "❌ Failed to start browser")
        
        elif line == "CLOSE_BROWSER":
            if phone_number in browser_sessions:
                if browser_sessions[phone_number].close_browser():
                    del browser_sessions[phone_number]
                    commands_executed.append("✅ Browser closed")
                    send_whatsapp_message(phone_number, "🔒 Magic Agent closed the browser")
                else:
                    commands_executed.append("❌ Failed to close browser")
            else:
                commands_executed.append("❌ No browser session found")
        
        elif any(line.startswith(cmd) for cmd in ["CLICK(", "SCROLL(", "TYPE(", "KEY(", "NAVIGATE("]) or line == "SCREENSHOT":
            if phone_number in browser_sessions:
                result = execute_browser_command(line, phone_number)
                commands_executed.append(f"🤖 {result}")
                
                # Send action notification to user
                action_desc = ""
                if line.startswith("CLICK("):
                    action_desc = f"🖱️ Magic Agent clicked at {line[6:-1]}"
                elif line.startswith("SCROLL("):
                    params = line[7:-1].split(",")
                    action_desc = f"📜 Magic Agent is scrolling {params[0]}..."
                elif line.startswith("TYPE("):
                    action_desc = f"⌨️ Magic Agent is typing..."
                elif line.startswith("KEY("):
                    action_desc = f"🔘 Magic Agent pressed {line[4:-1]}"
                elif line.startswith("NAVIGATE("):
                    action_desc = f"🌐 Magic Agent navigating to {line[9:-1]}"
                elif line == "SCREENSHOT":
                    action_desc = "📸 Magic Agent taking screenshot..."
                
                send_whatsapp_message(phone_number, action_desc)
                
                # Handle screenshot
                if result.startswith("SCREENSHOT_TAKEN:"):
                    screenshot_base64 = result[17:]  # Remove "SCREENSHOT_TAKEN:" prefix
                    send_whatsapp_image(phone_number, screenshot_base64, "📸 Current browser view")
            else:
                commands_executed.append("❌ No browser session found")
        
        elif line.startswith("ASK_USER("):
            question = line[9:-1]
            send_whatsapp_message(phone_number, f"❓ {question}")
        
        else:
            # Regular text response
            if line and not any(line.startswith(cmd) for cmd in ["START_BROWSER", "CLOSE_BROWSER", "CLICK(", "SCROLL(", "TYPE(", "KEY(", "NAVIGATE(", "SCREENSHOT", "ASK_USER("]):
                user_message += line + "\n"
    
    # Send regular response if any
    if user_message.strip():
        send_whatsapp_message(phone_number, user_message.strip())
    
    return screenshot_base64

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Webhook verification
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge
        else:
            return 'Forbidden', 403
    
    elif request.method == 'POST':
        # Handle incoming messages
        try:
            body = request.get_json()
            
            if (body.get('object') == 'whatsapp_business_account' and 
                body.get('entry') and 
                body['entry'][0].get('changes') and 
                body['entry'][0]['changes'][0].get('value') and 
                body['entry'][0]['changes'][0]['value'].get('messages')):
                
                messages = body['entry'][0]['changes'][0]['value']['messages']
                
                for message in messages:
                    phone_number = message['from']
                    
                    # Only process text messages
                    if message['type'] == 'text':
                        user_message = message['text']['body']
                        
                        print(f"Received message from {phone_number}: {user_message}")
                        
                        # Process in separate thread to avoid timeout
                        def process_message():
                            try:
                                # Get AI response
                                ai_response = get_ai_response(user_message, phone_number)
                                print(f"AI Response: {ai_response}")
                                
                                # Process AI response and execute commands
                                process_ai_response(ai_response, phone_number)
                                
                            except Exception as e:
                                print(f"Error processing message: {e}")
                                send_whatsapp_message(phone_number, "Sorry, I encountered an error processing your request.")
                        
                        # Start processing in background
                        threading.Thread(target=process_message).start()
                    
                    else:
                        # Send error for non-text messages
                        send_whatsapp_message(message['from'], "❌ I can only process text messages. Please send your request as text.")
            
            return jsonify({'status': 'success'}), 200
            
        except Exception as e:
            print(f"Webhook error: {e}")
            return jsonify({'status': 'error'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    print("🚀 Magic Agent WhatsApp Bot with Browser Automation Starting...")
    print("📱 Bot is ready to receive messages")
    print("🌐 Browser automation capabilities enabled")
    app.run(host='0.0.0.0', port=5000, debug=False)
