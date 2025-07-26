import os
import json
import requests
import time
import io
import traceback
import uuid
from urllib.parse import quote_plus, urlencode
from flask import Flask, request, Response, render_template_string, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO, join_room
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import google.generativeai as genai
import eventlet # Required for SocketIO production server

# Ensure eventlet is used
eventlet.monkey_patch()

# --- CONFIGURATION ---
GEMINI_API_KEYS = [
    # YOUR API KEYS HERE
]
WHATSAPP_TOKEN = "YOUR_WHATSAPP_TOKEN"
WHATSAPP_PHONE_NUMBER_ID = "YOUR_PHONE_NUMBER_ID"
VERIFY_TOKEN = "YOUR_VERIFY_TOKEN"
AI_MODEL_NAME = "gemini-1.5-flash"
ADMIN_NUMBER = "YOUR_ADMIN_NUMBER"

# App setup for SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_me'
socketio = SocketIO(app, async_mode='eventlet')

# Domain and WhatsApp Number for the UI
LIVE_VIEW_DOMAIN = "https://clicky.pyxelworld.com"
WHATSAPP_CONTACT_NUMBER = "+16095314294"
WHATSAPP_NUMBER_CLEANED = ''.join(filter(str.isdigit, WHATSAPP_CONTACT_NUMBER))

# --- PROJECT SETUP ---
BASE_DIR = Path(__file__).parent
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.txt"
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- CONSTANTS and SYSTEM PROMPT ---
CUSTOM_SEARCH_URL_BASE = "https://www.bing.com"
CUSTOM_SEARCH_URL_TEMPLATE = "https://www.bing.com/search?q=%s"
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800

SYSTEM_PROMPT = """
You are "Magic Clicky," a powerful AI that controls a web browser with high precision. You see the screen and choose the best command to achieve your goal.
--- YOUR CORE MECHANISM: DUAL-MODE CURSOR CONTROL ---
You control a **large red dot** (your virtual cursor). To interact, you MUST first move the cursor to the target, then act.
**1. Text Mode: `MOVE_CURSOR_TEXT`**: Provide text you see on screen. `{"command": "MOVE_CURSOR_TEXT", "params": {"text": "Login"}}`
**2. Coordinate Mode: `MOVE_CURSOR_COORDS`**: Use the grid to estimate (x, y) coordinates. `{"command": "MOVE_CURSOR_COORDS", "params": {"x": 120, "y": 455}}`
--- THE MANDATORY WORKFLOW: MOVE -> VERIFY -> ACT ---
1.  **MOVE:** Issue a `MOVE_CURSOR...` command.
2.  **VERIFY:** Examine the new screenshot. Is the red dot EXACTLY on your target?
3.  **ACT:** If correct, issue your action (`CLICK`, `TYPE`, etc.). If not, issue a new `MOVE_CURSOR...` command to correct it.
--- COMMAND REFERENCE ---
- `MOVE_CURSOR_TEXT`: {"text": "<text_on_screen>"}
- `MOVE_CURSOR_COORDS`: {"x": <int>, "y": <int>}
- `CLICK`: {}
- `TYPE`: {"text": "<text_to_type>", "enter": <true/false>} (Must CLICK an input field first)
- `CLEAR`: {}
- `SCROLL`: {"direction": "<up|down>"}
- `END_BROWSER`: {"reason": "<summary>"} (Task is fully complete)
- `NAVIGATE`: {"url": "<full_url>"}
- `CUSTOM_SEARCH`: {"query": "<search_term>"}
- `GO_BACK`: {}
- `WAIT`: {"seconds": <int>} (For loading content)
- `REFRESH_SCREEN`: {} (Just get a new view of the screen)
- `PAUSE_AND_ASK`: {"question": "<your_question>"} (Ask user for input)
- `SPEAK`: {"text": "<your_response>"} (For simple conversation)
--- GUIDING PRINCIPLES ---
- ALWAYS scroll down on a new page to see all content.
- IGNORE cookie banners and popups unless they block the main content.
- Use `NAVIGATE` to go directly to known URLs or construct search URLs (e.g., `https://google.com/search?q=query`). Avoid using search bars on pages if possible.
- Only "speak" what the user needs to know. Your thoughts are for you.
- Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.
"""

# --- HTML TEMPLATES ---
# (Omitted for brevity, but they are the same as the last correct version)
HOME_PAGE_TEMPLATE = """...""" # Paste the Home Page HTML here
LIVE_VIEW_TEMPLATE = """...""" # Paste the Live View HTML here


# --- HELPER FUNCTIONS ---

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp text message: {e} - {response.text}")

def send_whatsapp_document_by_id(to, media_id, caption="", filename="document.pdf"):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": {"id": media_id, "filename": filename, "caption": caption}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Forwarded document {media_id} to {to}")
    except requests.exceptions.RequestException as e:
        print(f"Error forwarding WhatsApp document: {e} - {response.text}")

def load_subscribers():
    if not SUBSCRIBERS_FILE.exists(): return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f: return {line.strip() for line in f if line.strip()}
    except IOError as e:
        print(f"CRITICAL: Could not read subscribers file: {e}")
        return set()
subscribers = load_subscribers()

def find_session_by_id(session_id):
    return next((session for session in user_sessions.values() if session.get('id') == session_id), None)

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try:
            prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e:
            return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error reading image: {e}"}, "thought": "Image read failed.", "speak": "Sorry, I had trouble seeing the screen."})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt_parts)
            print("AI call successful.")
            return response.text
        except Exception as e:
            print(f"API key #{i+1} failed. Error: {e}")
            last_error = e
            continue
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI API Error: {last_error}"}, "thought": "All AI API keys failed.", "speak": "I'm having trouble connecting to my brain right now. Please try again later."})

def find_text_in_ocr(ocr_results, target_text):
    if not ocr_results or not target_text: return None
    n_boxes = len(ocr_results.get('text', []))
    target_words = target_text.lower().split()
    if not target_words: return None

    for i in range(n_boxes):
        # ... [OCR text finding logic - unchanged] ...
        pass # Placeholder for the actual logic
    return None # If no match found

# --- CORE APPLICATION LOGIC ---

def create_new_session(identifier, prompt, session_type="whatsapp"):
    session_id = str(uuid.uuid4())
    user_dir = USER_DATA_DIR / session_id
    user_dir.mkdir(parents=True, exist_ok=True)
    session = {
        "id": session_id, "identifier": identifier, "session_type": session_type, "mode": "CHAT",
        "driver": None, "chat_history": [], "original_prompt": prompt, "user_dir": user_dir,
        "tab_handles": {}, "is_processing": False, "stop_requested": False, "interrupt_requested": False,
        "cursor_pos": (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2), "ocr_results": [],
        "last_status": "Session initialized. Waiting for prompt.", "last_screenshot_path": None,
        "view_link_sent": False, "live_view_updates_on": True
    }
    user_sessions[identifier] = session
    return session

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}")
    options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver
        session["mode"] = "BROWSER"
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        traceback.print_exc()
        return None

def close_browser(session, reason="Session closed by user."):
    if session.get("driver"):
        print(f"Closing browser for session {session['id']}")
        try:
            session["driver"].quit()
        except Exception as e:
            print(f"Error quitting driver: {e}")
        session["driver"] = None
    session["mode"] = "CHAT"
    session["is_processing"] = False
    session["stop_requested"] = True
    session["last_status"] = reason
    socketio.emit('session_ended', {'reason': reason}, room=session['id'])
    identifier = session['identifier']
    if identifier in user_sessions and user_sessions[identifier]['id'] == session['id']:
        print(f"Deleting session {session['id']} for {identifier} from memory.")
        del user_sessions[identifier]

def get_page_state(driver, session, status_message):
    screenshot_filename = "live_view.png"
    screenshot_path = session["user_dir"] / screenshot_filename
    session["last_screenshot_path"] = screenshot_path
    session["last_status"] = status_message
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        # ... [Drawing logic for grid and cursor - unchanged] ...
        draw = ImageDraw.Draw(image, 'RGBA')
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=20)
        except IOError: font = ImageFont.load_default()
        grid_color = (0, 0, 0, 100)
        for i in range(100, VIEWPORT_WIDTH, 100): draw.line([(i, 0), (i, VIEWPORT_HEIGHT)], fill=grid_color, width=1); draw.text((i + 2, 2), str(i), fill='red', font=font)
        for i in range(100, VIEWPORT_HEIGHT, 100): draw.line([(0, i), (VIEWPORT_WIDTH, i)], fill=grid_color, width=1); draw.text((2, i + 2), str(i), fill='red', font=font)
        cursor_x, cursor_y = session['cursor_pos']; radius = 16; outline_width = 4
        draw.ellipse([(cursor_x - radius, cursor_y - radius), (cursor_x + radius, cursor_y + radius)], fill='white')
        draw.ellipse([(cursor_x - (radius-outline_width), cursor_y-(radius-outline_width)), (cursor_x+(radius-outline_width), cursor_y+(radius-outline_width))], fill='red')
        image.save(screenshot_path)

        update_data = {
            'status': status_message,
            'image_path': f"/images/{session['id']}/{screenshot_filename}"
        }
        socketio.emit('session_update', update_data, room=session['id'])
        
        # ... [Tab info logic - unchanged] ...
        return screenshot_path, "Tab info gathered"
    except Exception as e:
        print(f"Error getting page state: {e}")
        return None, "Error getting page state."

def process_next_browser_step(session, caption):
    if session.get("stop_requested"): return
    from_number = session['identifier'] if session['session_type'] == 'whatsapp' else None
    if session['session_type'] == 'web':
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': caption}}, room=session['id'])
    if from_number and not session.get('live_view_updates_on', True):
        send_whatsapp_message(from_number, caption)
    screenshot_path, tab_info_text = get_page_state(session["driver"], session, caption)
    if not session.get("view_link_sent"):
        live_view_url = f"{LIVE_VIEW_DOMAIN}/view/{session['id']}"
        if from_number:
            send_whatsapp_message(from_number, f"I'm starting! Follow and control the session in real-time here:\n{live_view_url}")
        session["view_link_sent"] = True
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\nPrevious Action: {caption}\n{tab_info_text}"
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(session, ai_response)
    else:
        error_msg = "Could not capture the browser screen. Ending the session for safety."
        if from_number: send_whatsapp_message(from_number, error_msg)
        close_browser(session, reason=error_msg)

def process_ai_command(session, ai_response_text):
    if session.get("stop_requested"): return {}
    try:
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        error_message = f"AI responded with invalid format: {ai_response_text}"
        print(error_message)
        socketio.start_background_task(process_next_browser_step, session, error_message)
        return {}

    command = command_data.get("command")
    params = command_data.get("params", {})
    speak = command_data.get("speak", "")

    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak:
        if session['session_type'] == 'whatsapp': send_whatsapp_message(session['identifier'], speak)
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': speak}}, room=session['id'])

    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "END_BROWSER", "PAUSE_AND_ASK"]:
        driver = start_browser(session)
        if not driver:
            close_browser(session, "Critical failure: Could not start browser.")
            return {}

    action_in_browser = True
    next_step_caption = f"Action: {command}"
    try:
        # ### THIS IS THE CORRECTED IF/ELIF/ELSE BLOCK ###
        if command == "END_BROWSER":
            reason = params.get('reason', 'N/A')
            close_browser(session, f"Task Completed. Summary: {reason}")
            if session['session_type'] == 'whatsapp':
                send_whatsapp_message(session['identifier'], f"*Task Completed.*\n*Summary:* {reason}")
            return command_data
        elif command == "CLICK":
             pass # Add CLICK logic here
        # ... Add all other elif command blocks here ...
        else:
            # THIS IS THE FIX. If the command is unknown, we do nothing and proceed.
            # The 'pass' keyword is a placeholder that does nothing.
            next_step_caption = f"Unknown command: {command}"
            action_in_browser = False
            pass
        
        if action_in_browser: time.sleep(2)
        socketio.start_background_task(process_next_browser_step, session, next_step_caption)

    except Exception as e:
        error_summary = f"Error running '{command}': {e}"
        traceback.print_exc()
        socketio.start_background_task(process_next_browser_step, session, error_summary)
    return command_data


# --- FLASK ROUTES AND WEBSOCKETS ---

@app.route('/')
def home():
    # Make sure to paste your HOME_PAGE_TEMPLATE html into the string below
    return render_template_string("""...""", whatsapp_number=WHATSAPP_NUMBER_CLEANED)

@app.route('/start-web-session', methods=['POST'])
def start_web_session():
    prompt = request.form.get('prompt')
    if not prompt: return "Prompt is required.", 400
    session_id = str(uuid.uuid4())
    session = create_new_session(identifier=session_id, prompt=prompt, session_type="web")
    session['is_processing'] = True
    socketio.start_background_task(target=run_initial_ai, session=session, user_message=prompt)
    return redirect(url_for('view_session', session_id=session.get('id')))

def run_initial_ai(session, user_message):
    session["chat_history"].append({"role": "user", "parts": [user_message]})
    ai_response = call_ai(session["chat_history"], context_text=f"New task: {user_message}")
    process_ai_command(session, ai_response)

@app.route('/view/<session_id>')
def view_session(session_id):
    if not find_session_by_id(session_id): return "Session not found or has expired.", 404
    # Make sure to paste your LIVE_VIEW_TEMPLATE html into the string below
    return render_template_string("""...""", session_id=session_id)

@app.route('/images/<session_id>/<filename>')
def serve_image(session_id, filename):
    directory = USER_DATA_DIR / session_id
    if not (directory / filename).exists(): return "Image not found.", 404
    return send_from_directory(directory, filename)

@socketio.on('join')
def on_join(data):
    session_id = data['session_id']
    join_room(session_id)
    print(f"Client joined room: {session_id}")

@socketio.on('user_command')
def handle_user_command(data):
    session = find_session_by_id(data.get('session_id'))
    if not session: return
    command = data.get('command')
    value = data.get('value')
    if command == 'message':
        if session.get("is_processing"):
            socketio.emit('session_update', {'log_message': {'sender':'ai', 'text':"Working... please Interrupt first."}}, room=session['id'])
            return
        session['is_processing'] = True
        session["chat_history"].append({"role": "user", "parts": [value]})
        socketio.start_background_task(process_next_browser_step, session, f"User Guidance: {value}")
    elif command == 'interrupt':
        session['interrupt_requested'] = True
        session['is_processing'] = False
        socketio.emit('session_update', {'status': 'Interrupted. Ready for new command.'}, room=session['id'])
    elif command == 'stop':
        close_browser(session, reason="Session stopped by user via web interface.")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # ... [Webhook logic - unchanged] ...
    pass # Placeholder

if __name__ == '__main__':
    print("--- Magic Clicky Server with Web UI & Live Control ---")
    socketio.run(app, host='0.0.0.0', port=5000)
