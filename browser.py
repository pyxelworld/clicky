from flask import Flask, request, jsonify
import requests
import json
import os
import time
import base64
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, WebDriverException
import google.generativeai as genai  # Assuming the library is installed; user has requirements.

app = Flask(__name__)

# Provided credentials
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# Model name as specified by user
MODEL_NAME = "gemini-2.0-flash"

# Directories
PROFILES_DIR = "profiles"
DOWNLOADS_DIR = "downloads"
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Sessions: phone_number -> {'history': [], 'browser': webdriver or None, 'profile_dir': str, 'download_dir': str, 'active': bool}
sessions = {}

# System prompt for the AI
SYSTEM_PROMPT = """
You are Magic Agent, an AI assistant that can converse normally with users and also control a web browser to perform tasks.

For normal conversation: Respond helpfully to user queries without browser involvement.

For browser tasks: You can start a browser session when needed. You will receive screenshots of the browser as base64 images in the prompt. Analyze the screenshot and decide on actions.

Commands: To perform actions, include exactly one command per response in this format: [COMMAND: action params]
- After a command, do not add extra text unless it's a response to the user.
- If you need to ask the user for more info, use [COMMAND: ask_user "Your question here"]
- To end browser and respond to user, use [COMMAND: end_browser "Your final response here"]

Available commands:
- start_browser "url": Starts a new browser session and navigates to the URL. If no URL, defaults to google.com.
- close_browser: Closes the browser session.
- click x y: Clicks at coordinates x,y on the current screenshot (0,0 is top-left).
- scroll direction amount: Direction can be "down", "up", "left", "right". Amount in pixels (e.g., 500).
- type "text": Types the text into the focused element. First click to focus if needed.
- press_key "key": Presses a keyboard key or shortcut, e.g., "ENTER", "CTRL+T" for new tab, "CTRL+W" for close tab.
- open_tab "url": Opens a new tab with the URL.
- close_tab: Closes the current tab.
- switch_tab index: Switches to tab by index (0-based).
- download "url" "filename": Downloads a file from URL to user's folder, named filename.
- ask_user "question": Pauses browser actions and asks the user the question via WhatsApp.
- end_browser "response": Ends the browser session and sends the response to the user.

Browser flow:
- After starting, you'll get a screenshot.
- Respond with a command based on the screenshot.
- The system will execute it, send you a new screenshot, and prompt again.
- Repeat until you end_browser or close_browser.
- For tasks requiring multiple steps, issue one command at a time.
- Always analyze the screenshot to decide coordinates for clicks, etc.

Remember: One command per response. After command execution, user gets a screenshot and action description on WhatsApp.
"""

# Configure Gemini (using the library; adjust if needed for REST, but assuming genai works without configure)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# Function to send message to WhatsApp
def send_whatsapp_message(to, text, image_data=None):
    url = f"https://graph.facebook.com/v13.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    if image_data:
        # For images, we need to upload media first
        media_url = upload_whatsapp_media(image_data)
        if media_url:
            data["type"] = "image"
            data["image"] = {"link": media_url}
        else:
            # Fallback to text if upload fails
            data["text"]["body"] += "\n(Failed to attach screenshot)"
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# Function to upload media to WhatsApp (for screenshots)
def upload_whatsapp_media(image_data):
    url = f"https://graph.facebook.com/v13.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }
    files = {
        "file": ("screenshot.png", image_data, "image/png"),
        "type": (None, "image/png"),
        "messaging_product": (None, "whatsapp")
    }
    response = requests.post(url, headers=headers, files=files)
    if response.status_code == 200:
        return response.json().get("id")  # Actually, for sending, we use link? Wait, WhatsApp API for images can use link or ID? Adjust.
        # Note: WhatsApp Business API allows sending by link if hosted, but for upload, it's ID for attachment.
        # Correction: After upload, you get media ID, then send with "id": media_id
        return response.json().get("id")
    return None

# In send_whatsapp_message, adjust for media ID
# Actually, updating the function:
def send_whatsapp_message(to, text, image_data=None):
    url = f"https://graph.facebook.com/v13.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to
    }
    if image_data:
        media_id = upload_whatsapp_media(image_data)
        if media_id:
            data["type"] = "image"
            data["image"] = {"id": media_id, "caption": text}
        else:
            data["type"] = "text"
            data["text"] = {"body": text + "\n(Failed to attach screenshot)"}
    else:
        data["type"] = "text"
        data["text"] = {"body": text}
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# Function to take screenshot of browser
def take_screenshot(driver):
    png = driver.get_screenshot_as_png()
    return png

# Function to send prompt to Gemini with optional image
def query_gemini(history, user_message, image_base64=None):
    prompt_parts = [SYSTEM_PROMPT] + history + [user_message]
    if image_base64:
        prompt_parts.append({"mime_type": "image/png", "data": image_base64})
    
    response = model.generate_content(prompt_parts)
    return response.text

# Function to parse command from AI response
def parse_command(response):
    if "[COMMAND:" in response:
        cmd_part = response.split("[COMMAND:")[1].split("]")[0].strip()
        parts = cmd_part.split(" ", 1)
        action = parts[0]
        params = parts[1] if len(parts) > 1 else ""
        return action, params
    return None, None

# Function to execute browser command
def execute_browser_command(phone_number, action, params, driver):
    description = ""
    if action == "start_browser":
        url = params.strip('"') or "https://google.com"
        profile_dir = os.path.join(PROFILES_DIR, phone_number)
        download_dir = os.path.join(DOWNLOADS_DIR, phone_number)
        os.makedirs(profile_dir, exist_ok=True)
        os.makedirs(download_dir, exist_ok=True)
        
        options = Options()
        options.binary_location = "/usr/bin/google-chrome"  # Explicitly set to avoid error
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument(f"--profile-directory=Default")
        options.add_experimental_option("prefs", {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        })
        # Headless? But for screenshots, can be headless.
        options.add_argument("--headless")  # Since terminal-only, run headless
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")  # Set a size for consistent screenshots
        
        service = Service(executable_path="/usr/local/bin/chromedriver")  # Assume path; adjust if needed
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        sessions[phone_number]['browser'] = driver
        description = f"Magic Agent started browser at {url}"
    
    elif action == "close_browser":
        if driver:
            driver.quit()
            sessions[phone_number]['browser'] = None
        description = "Magic Agent closed the browser"
    
    elif action == "click":
        x, y = map(int, params.split())
        ActionChains(driver).move_by_offset(x, y).click().perform()
        ActionChains(driver).reset_actions()  # Reset
        description = f"Magic Agent clicked at ({x}, {y})"
    
    elif action == "scroll":
        dir, amt = params.split()
        amt = int(amt)
        if dir == "down":
            driver.execute_script(f"window.scrollBy(0, {amt});")
        elif dir == "up":
            driver.execute_script(f"window.scrollBy(0, -{amt});")
        elif dir == "left":
            driver.execute_script(f"window.scrollBy(-{amt}, 0);")
        elif dir == "right":
            driver.execute_script(f"window.scrollBy({amt}, 0);")
        description = f"Magic Agent scrolled {dir} by {amt} pixels"
    
    elif action == "type":
        text = params.strip('"')
        driver.switch_to.active_element.send_keys(text)
        description = f"Magic Agent typed: {text}"
    
    elif action == "press_key":
        key = params.strip('"')
        # Handle shortcuts like CTRL+T
        if '+' in key:
            keys = key.split('+')
            action_chain = ActionChains(driver)
            for k in keys[:-1]:
                action_chain.key_down(eval(f"Keys.{k.upper()}"))
            action_chain.send_keys(eval(f"Keys.{keys[-1].upper()}"))
            for k in reversed(keys[:-1]):
                action_chain.key_up(eval(f"Keys.{k.upper()}"))
            action_chain.perform()
        else:
            driver.switch_to.active_element.send_keys(eval(f"Keys.{key.upper()}"))
        description = f"Magic Agent pressed key: {key}"
    
    elif action == "open_tab":
        url = params.strip('"')
        driver.execute_script(f"window.open('{url}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        description = f"Magic Agent opened new tab at {url}"
    
    elif action == "close_tab":
        driver.close()
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
        description = "Magic Agent closed the current tab"
    
    elif action == "switch_tab":
        index = int(params)
        if index < len(driver.window_handles):
            driver.switch_to.window(driver.window_handles[index])
        description = f"Magic Agent switched to tab {index}"
    
    elif action == "download":
        url, filename = params.strip('"').split('" "')
        filename = filename.strip('"')
        download_path = os.path.join(sessions[phone_number]['download_dir'], filename)
        with requests.get(url, stream=True) as r:
            with open(download_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        description = f"Magic Agent downloaded {filename} from {url}"
    
    return driver, description

# Webhook endpoint
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        return "Verification failed", 403
    
    if request.method == 'POST':
        data = request.get_json()
        if 'entry' in data and data['entry'][0]['changes'][0]['value'].get('messages'):
            message = data['entry'][0]['changes'][0]['value']['messages'][0]
            phone_number = message['from']
            if message['type'] != 'text':
                send_whatsapp_message(phone_number, "Error: Only text messages are supported.")
                return jsonify({"status": "ok"}), 200
            
            user_message = message['text']['body']
            
            if phone_number not in sessions:
                sessions[phone_number] = {
                    'history': [],
                    'browser': None,
                    'profile_dir': os.path.join(PROFILES_DIR, phone_number),
                    'download_dir': os.path.join(DOWNLOADS_DIR, phone_number),
                    'active': True
                }
            
            session = sessions[phone_number]
            session['history'].append(f"User: {user_message}")
            
            # If browser active, prepare screenshot
            image_base64 = None
            if session['browser']:
                screenshot = take_screenshot(session['browser'])
                image_base64 = base64.b64encode(screenshot).decode('utf-8')
            
            ai_response = query_gemini(session['history'], f"User: {user_message}", image_base64)
            
            # Parse for command
            action, params = parse_command(ai_response)
            
            browser_active = bool(session['browser'])
            while action:  # Loop for commands until no more or special
                if action == "ask_user":
                    question = params.strip('"')
                    send_whatsapp_message(phone_number, question)
                    session['history'].append(f"Magic Agent: {ai_response}")
                    return jsonify({"status": "ok"}), 200
                
                elif action == "end_browser":
                    response_text = params.strip('"')
                    if session['browser']:
                        session['browser'].quit()
                        session['browser'] = None
                    send_whatsapp_message(phone_number, response_text)
                    session['history'].append(f"Magic Agent: {response_text}")
                    return jsonify({"status": "ok"}), 200
                
                else:
                    # Execute browser command
                    try:
                        session['browser'], description = execute_browser_command(phone_number, action, params, session['browser'])
                        # Take new screenshot
                        if session['browser']:
                            new_screenshot = take_screenshot(session['browser'])
                            # Send to user
                            send_whatsapp_message(phone_number, description, new_screenshot)
                            # Prepare base64 for next AI prompt
                            image_base64 = base64.b64encode(new_screenshot).decode('utf-8')
                        else:
                            send_whatsapp_message(phone_number, description)
                        
                        # Now prompt AI again with new state
                        session['history'].append(f"System: Command executed: {description}")
                        ai_response = query_gemini(session['history'], "Continue based on new screenshot.", image_base64)
                        action, params = parse_command(ai_response)
                    except Exception as e:
                        error_msg = f"Error executing command: {str(e)}"
                        send_whatsapp_message(phone_number, error_msg)
                        if session['browser']:
                            session['browser'].quit()
                            session['browser'] = None
                        session['history'].append(f"System: {error_msg}")
                        return jsonify({"status": "ok"}), 200
            
            # If no command, it's a normal response
            if not browser_active or not action:
                send_whatsapp_message(phone_number, ai_response)
                session['history'].append(f"Magic Agent: {ai_response}")
            
        return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
