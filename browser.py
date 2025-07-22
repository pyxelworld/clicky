import os
import json
import requests
import base64
import logging
from io import BytesIO

from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from PIL import Image, ImageDraw, ImageFont

import google.generativeai as genai

# --- CONFIGURATION ---
# User-provided credentials (for testing purposes)
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
HOST_URL = "https://your-cloudflared-url.io" # IMPORTANT: Replace with your Cloudflare Tunnel URL

# Constants
USER_DATA_DIR = "user_data"
CHROME_BINARY_LOCATION = "/usr/bin/google-chrome"
MODEL_NAME = 'gemini-1.5-flash-latest' # Using the official, working model name for multimodality.

# --- AI SYSTEM PROMPT ---
MAGIC_AGENT_PROMPT = """
You are "Magic Agent", a powerful AI assistant with the ability to control a web browser to accomplish tasks for a user.

You operate in a loop: you receive a screenshot of the current browser page and the user's objective, and you must respond with a single action command in JSON format.

The user will interact with you via WhatsApp. When you are in a browser session, you will not chat. You will only execute commands to complete the task.

The browser window is 1280x720. The screenshots you see have a grid overlayed with coordinates to help you specify locations for clicks.

**AVAILABLE COMMANDS:**

1.  **GOTO**: Navigate to a specific URL.
    {"command": "GOTO", "url": "https://www.google.com"}

2.  **CLICK**: Clicks on a specific coordinate on the page. Use this for buttons, links, and text fields.
    {"command": "CLICK", "x": 550, "y": 320}

3.  **TYPE**: Types text into the currently active element (you must CLICK it first).
    {"command": "TYPE", "text": "What is the weather in Belo Horizonte?"}

4.  **SCROLL**: Scrolls the page up or down.
    {"command": "SCROLL", "direction": "down"}

5.  **PRESS_KEY**: Simulates pressing a special key on the keyboard.
    {"command": "PRESS_KEY", "key": "ENTER"}

6.  **ASK_USER**: If you need more information from the user to proceed. This will pause the browser session.
    {"command": "ASK_USER", "question": "I found multiple products. Which one are you interested in?"}

7.  **END_BROWSER**: When the task is fully completed. Provide a summary of what you did.
    {"command": "END_BROWSER", "reason": "I have successfully found the weather forecast and sent it to you."}

**RULES:**
-   Respond ONLY with a valid JSON object containing one of the commands above.
-   Do not add any explanations or conversational text outside of the JSON.
-   Analyze the screenshot carefully to determine the correct coordinates and actions.
-   A user's message during a browser session should be treated as an additional instruction for the current task.
-   To start a browser session, the user's initial prompt must describe a task for you to perform on the web.
"""

# --- GLOBAL SESSION MANAGEMENT ---
SESSIONS = {}

# --- FLASK APP SETUP ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- GOOGLE GEMINI SETUP ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
except Exception as e:
    logging.error(f"Failed to configure Gemini: {e}")
    model = None

# --- WHATSAPP HELPER FUNCTIONS ---
def send_whatsapp_message(to, text):
    """Sends a simple text message."""
    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logging.info(f"Message sent to {to}: {response.json()}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send message to {to}: {e.response.text}")

def upload_whatsapp_media(image_bytes):
    """Uploads media to WhatsApp servers and returns the media ID."""
    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': ('screenshot.png', image_bytes, 'image/png')}
    form_data = {'messaging_product': 'whatsapp'}
    try:
        response = requests.post(url, headers=headers, files=files, data=form_data)
        response.raise_for_status()
        media_id = response.json().get("id")
        logging.info(f"Media uploaded successfully. ID: {media_id}")
        return media_id
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to upload media: {e.response.text}")
        return None

def send_whatsapp_image(to, image_bytes, caption):
    """Uploads and sends an image with a caption."""
    media_id = upload_whatsapp_media(image_bytes)
    if not media_id:
        send_whatsapp_message(to, f"{caption}\n\n[Could not display screenshot]")
        return

    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "image",
        "image": {"id": media_id, "caption": caption}
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logging.info(f"Image message sent to {to}: {response.json()}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send image message to {to}: {e.response.text}")

# --- BROWSER AUTOMATION (SELENIUM) ---
def start_browser(phone_number):
    """Initializes a new Chrome browser instance for a user."""
    session = SESSIONS.get(phone_number, {})
    if session.get("driver"):
        logging.info(f"Browser already running for {phone_number}")
        return session["driver"]

    profile_path = os.path.join(USER_DATA_DIR, phone_number, "profile")
    download_path = os.path.join(USER_DATA_DIR, phone_number, "downloads")
    os.makedirs(profile_path, exist_ok=True)
    os.makedirs(download_path, exist_ok=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,720")
    options.add_argument(f"--user-data-dir={profile_path}")
    options.binary_location = CHROME_BINARY_LOCATION

    prefs = {"download.default_directory": os.path.abspath(download_path)}
    options.add_experimental_option("prefs", prefs)

    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver
        session["browser_active"] = True
        SESSIONS[phone_number] = session
        logging.info(f"Browser started for {phone_number}")
        return driver
    except Exception as e:
        logging.error(f"Failed to start Chrome for {phone_number}: {e}")
        return None

def close_browser(phone_number):
    """Closes the browser and cleans up the session."""
    session = SESSIONS.get(phone_number)
    if session and session.get("driver"):
        try:
            session["driver"].quit()
        except Exception as e:
            logging.error(f"Error quitting driver for {phone_number}: {e}")
        session["driver"] = None
        session["browser_active"] = False
        logging.info(f"Browser closed for {phone_number}")

def capture_and_prepare_screenshot(driver):
    """Captures a screenshot, adds a grid, and returns it as bytes."""
    png_data = driver.get_screenshot_as_png()
    image = Image.open(BytesIO(png_data))
    draw = ImageDraw.Draw(image)
    
    # Load a font or use default
    try:
        font = ImageFont.truetype("sans-serif.ttf", 12)
    except IOError:
        font = ImageFont.load_default()

    # Draw grid and coordinates
    w, h = image.size
    for i in range(0, w, 100):
        draw.line([(i, 0), (i, h)], fill=(255, 0, 0, 128), width=1)
        draw.text((i + 2, 2), str(i), fill="red", font=font)
    for i in range(0, h, 100):
        draw.line([(0, i), (w, i)], fill=(255, 0, 0, 128), width=1)
        draw.text((2, i + 2), str(i), fill="red", font=font)
        
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def execute_agent_command(phone_number, command_json):
    """Parses and executes the command from the AI."""
    session = SESSIONS.get(phone_number, {})
    driver = session.get("driver")
    if not driver:
        send_whatsapp_message(phone_number, "Error: Browser is not running.")
        return

    try:
        command = json.loads(command_json)
        cmd = command.get("command")
        logging.info(f"Executing command for {phone_number}: {cmd}")

        action_description = ""
        user_message_after_action = True

        if cmd == "GOTO":
            url = command.get("url")
            driver.get(url)
            action_description = f"Magic Agent is navigating to: {url}"
        elif cmd == "CLICK":
            x, y = command.get("x"), command.get("y")
            # Using JavaScript to click at coordinates is more reliable in headless mode
            driver.execute_script("document.elementFromPoint(arguments[0], arguments[1]).click();", x, y)
            action_description = f"Magic Agent clicked at ({x}, {y})."
        elif cmd == "TYPE":
            text = command.get("text")
            ActionChains(driver).send_keys(text).perform()
            action_description = f"Magic Agent typed: '{text}'"
        elif cmd == "SCROLL":
            direction = command.get("direction", "down")
            scroll_amount = 500 if direction == "down" else -500
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            action_description = f"Magic Agent is scrolling {direction}."
        elif cmd == "PRESS_KEY":
            key = command.get("key").upper()
            ActionChains(driver).send_keys(getattr(Keys, key)).perform()
            action_description = f"Magic Agent pressed the {key} key."
        elif cmd == "ASK_USER":
            question = command.get("question")
            session["browser_active"] = False # Pause browser mode to wait for user reply
            send_whatsapp_message(phone_number, question)
            user_message_after_action = False
        elif cmd == "END_BROWSER":
            reason = command.get("reason")
            send_whatsapp_message(phone_number, f"✨ Task complete! ✨\n\nMagic Agent reports: {reason}")
            close_browser(phone_number)
            user_message_after_action = False
        else:
            send_whatsapp_message(phone_number, "Magic Agent sent an unknown command.")
            user_message_after_action = False
        
        # After a successful action, send screenshot update
        if user_message_after_action:
            screenshot_bytes = capture_and_prepare_screenshot(driver)
            send_whatsapp_image(phone_number, screenshot_bytes, action_description)
            # Trigger next AI step immediately
            process_browser_interaction(phone_number, "Continue with the task.")

    except json.JSONDecodeError:
        logging.error(f"AI returned invalid JSON: {command_json}")
        send_whatsapp_message(phone_number, "Magic Agent had a technical issue (Invalid command format). Please try again.")
        close_browser(phone_number)
    except Exception as e:
        logging.error(f"Error executing command for {phone_number}: {e}")
        send_whatsapp_message(phone_number, f"Magic Agent encountered an error: {e}")
        close_browser(phone_number)

# --- CORE AI INTERACTION LOGIC ---
def process_browser_interaction(phone_number, user_text):
    """Handles the back-and-forth between screenshot, AI, and action."""
    session = SESSIONS.get(phone_number, {})
    driver = session.get("driver")

    if not driver or not model:
        send_whatsapp_message(phone_number, "The agent is not available right now. Please try again later.")
        return

    # Add user's latest message to history
    session.setdefault("history", []).append({"role": "user", "parts": [user_text]})

    send_whatsapp_message(phone_number, "Magic Agent is thinking... 🤔")

    # Capture screenshot for the AI
    screenshot_bytes = capture_and_prepare_screenshot(driver)
    screenshot_part = {"mime_type": "image/png", "data": screenshot_bytes}

    # Construct the prompt for Gemini
    prompt_history = [
        {"role": "user", "parts": [MAGIC_AGENT_PROMPT]},
        {"role": "model", "parts": ["Understood. I am Magic Agent. I will only respond with JSON commands."]}
    ]
    prompt_history.extend(session["history"])
    prompt_history.append({"role": "user", "parts": [screenshot_part, f"Current Task: {session.get('task')}"]})
    
    try:
        response = model.generate_content(prompt_history)
        ai_command_json = response.text.strip().replace("```json", "").replace("```", "")
        
        # Log AI response and add to history
        logging.info(f"AI response for {phone_number}: {ai_command_json}")
        session["history"].append({"role": "model", "parts": [ai_command_json]})

        # Execute the command
        execute_agent_command(phone_number, ai_command_json)

    except Exception as e:
        logging.error(f"Error calling Gemini API for {phone_number}: {e}")
        send_whatsapp_message(phone_number, "Magic Agent is having trouble connecting to its brain. Please try again.")
        close_browser(phone_number)

# --- FLASK WEBHOOK ---
@app.route("/", methods=["GET"])
def verify_token():
    """Handles webhook verification."""
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Invalid verification token", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    """Main webhook to receive WhatsApp messages."""
    data = request.get_json()
    logging.info(f"Received data: {json.dumps(data, indent=2)}")

    if "entry" not in data or "changes" not in data["entry"][0]:
        return "OK", 200
        
    change = data["entry"][0]["changes"][0]
    if "messages" not in change["value"]:
        return "OK", 200

    message_data = change["value"]["messages"][0]
    phone_number = message_data["from"]
    message_type = message_data["type"]

    if message_type != "text":
        send_whatsapp_message(phone_number, "Sorry, I can only process text messages.")
        return "OK", 200

    user_text = message_data["text"]["body"]

    # Initialize session if it's a new user
    if phone_number not in SESSIONS:
        SESSIONS[phone_number] = {
            "browser_active": False,
            "driver": None,
            "history": [],
            "task": ""
        }
        send_whatsapp_message(phone_number, "Welcome! I am Magic Agent. ✨\n\nDescribe a task you want me to perform on the web, and I'll start my browser.")

    session = SESSIONS[phone_number]

    if session.get("browser_active"):
        # If the browser is already running, this is an additional instruction
        process_browser_interaction(phone_number, user_text)
    else:
        # Browser is not active. User is either starting a new task or replying to a question.
        session["browser_active"] = True # Assume we are starting a browser session
        session["task"] = user_text # The user's message is the main task
        session["history"] = [] # Reset history for the new task

        send_whatsapp_message(phone_number, f"🚀 Roger that! Starting browser for task: \"{user_text}\"")
        driver = start_browser(phone_number)
        if driver:
            driver.get("https://www.google.com")
            # Start the interaction loop
            process_browser_interaction(phone_number, "Start the task.")
        else:
            send_whatsapp_message(phone_number, "I'm sorry, I failed to start the browser. Please check the server logs.")
            session["browser_active"] = False

    return "OK", 200

# --- RUN THE APP ---
if __name__ == "__main__":
    if not HOST_URL or "your-cloudflared-url" in HOST_URL:
        logging.warning("HOST_URL is not set. Image sending might not work correctly without a public URL.")
    app.run(port=8080, debug=True)

