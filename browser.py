# FIX 1: Eventlet monkey patching must happen first.
import eventlet
eventlet.monkey_patch()

# Standard library imports
import os
import json
import requests
import time
import io
import traceback
import uuid
from urllib.parse import quote_plus, urlencode

# Third-party imports
from flask import Flask, request, Response, render_template_string, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import google.generativeai as genai

# --- CONFIGURATION ---
# (Fill these with your actual credentials)
GEMINI_API_KEYS = []
WHATSAPP_TOKEN = ""
WHATSAPP_PHONE_NUMBER_ID = ""
VERIFY_TOKEN = ""
AI_MODEL_NAME = "gemini-1.5-flash"
ADMIN_NUMBER = ""

# --- APP SETUP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_me_for_production'
socketio = SocketIO(app, async_mode='eventlet')

LIVE_VIEW_DOMAIN = "https://clicky.pyxelworld.com"
WHATSAPP_CONTACT_NUMBER = "+16095314294"
WHATSAPP_NUMBER_CLEANED = ''.join(filter(str.isdigit, WHATSAPP_CONTACT_NUMBER))

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
SYSTEM_PROMPT = """You are "Magic Clicky,"... (Full prompt as before)"""
HOME_PAGE_TEMPLATE = """... (Full HTML as before)"""
LIVE_VIEW_TEMPLATE = """... (Full HTML as before)"""

# --- HELPER FUNCTIONS ---

def send_whatsapp_message(to, text):
    if not WHATSAPP_TOKEN: return
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp text message: {e}")

def load_subscribers():
    if not SUBSCRIBERS_FILE.exists(): return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f: return {line.strip() for line in f if line.strip()}
    except IOError as e: print(f"CRITICAL: Could not read subscribers file: {e}"); return set()
subscribers = load_subscribers()

def find_session_by_id(session_id):
    return next((session for session in user_sessions.values() if session.get('id') == session_id), None)

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error reading image: {e}"}})
    last_error = "No API keys provided."
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt_parts)
            return response.text
        except Exception as e: last_error = e; continue
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI API Error: {last_error}"}})

def find_text_in_ocr(ocr_results, target_text):
    if not ocr_results or not target_text: return None
    # ... (Actual OCR logic would go here)
    return None

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
        "view_link_sent": False, "live_view_updates_on": True, "sid": None # FIX 2: Add sid field
    }
    user_sessions[identifier] = session
    return session

def start_browser(session):
    if session.get("driver"): return session["driver"]
    options = Options()
    options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver; session["mode"] = "BROWSER"; return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); return None

def close_browser(session, reason="Session closed by user."):
    if session.get("driver"):
        try: session["driver"].quit()
        except Exception as e: print(f"Error quitting driver: {e}")
    session.update({"driver": None, "mode": "CHAT", "is_processing": False, "stop_requested": True, "last_status": reason})
    socketio.emit('session_ended', {'reason': reason}, room=session['id'])
    identifier = session['identifier']
    if identifier in user_sessions and user_sessions[identifier]['id'] == session['id']:
        del user_sessions[identifier]

def get_page_state(driver, session, status_message):
    screenshot_filename = "live_view.png"
    screenshot_path = session["user_dir"] / screenshot_filename
    session.update({"last_screenshot_path": screenshot_path, "last_status": status_message})
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image, 'RGBA')
        # ... (drawing logic here)
        image.save(screenshot_path)
        update_data = {'status': status_message, 'image_path': f"/images/{session['id']}/{screenshot_filename}"}
        socketio.emit('session_update', update_data, room=session['id'])
        return screenshot_path, "Tab info gathered"
    except Exception as e: print(f"Error getting page state: {e}"); return None, "Error getting page state."

def process_next_browser_step(session, caption):
    if session.get("stop_requested"): return
    from_number = session['identifier'] if session['session_type'] == 'whatsapp' else None
    if session['session_type'] == 'web':
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': caption}}, room=session['id'])
    if from_number and not session.get('live_view_updates_on', True): send_whatsapp_message(from_number, caption)
    if not session.get("view_link_sent"):
        live_view_url = f"{LIVE_VIEW_DOMAIN}/view/{session['id']}"
        if from_number: send_whatsapp_message(from_number, f"I'm starting! Follow and control the session in real-time here:\n{live_view_url}")
        session["view_link_sent"] = True
    screenshot_path, tab_info_text = get_page_state(session["driver"], session, caption)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\nPrevious Action: {caption}\n{tab_info_text}"
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(session, ai_response)
    else: close_browser(session, reason="Could not capture the browser screen.")

def process_ai_command(session, ai_response_text):
    if session.get("stop_requested"): return {}
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        error_message = f"AI responded with invalid format: {ai_response_text}"
        socketio.start_background_task(process_next_browser_step, session, error_message); return {}
    command, params, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("speak", "")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak:
        if session['session_type'] == 'whatsapp': send_whatsapp_message(session['identifier'], speak)
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': speak}}, room=session['id'])
    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "END_BROWSER", "PAUSE_AND_ASK"]:
        driver = start_browser(session)
        if not driver: close_browser(session, "Critical failure: Could not start browser."); return {}
    action_in_browser = True
    next_step_caption = f"Action: {command}"
    try:
        # (This is where the full if/elif block for all commands would go)
        if command == "END_BROWSER": close_browser(session, f"Task Completed. Summary: {params.get('reason', 'N/A')}"); return
        else: action_in_browser = False # Simplified for brevity
        if action_in_browser: time.sleep(2)
        socketio.start_background_task(process_next_browser_step, session, next_step_caption)
    except Exception as e:
        error_summary = f"Error running '{command}': {e}"
        socketio.start_background_task(process_next_browser_step, session, error_summary)

# --- FLASK ROUTES AND WEBSOCKETS ---

@app.route('/')
def home(): return render_template_string(HOME_PAGE_TEMPLATE, whatsapp_number=WHATSAPP_NUMBER_CLEANED)

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
    return render_template_string(LIVE_VIEW_TEMPLATE, session_id=session_id)

@app.route('/images/<session_id>/<filename>')
def serve_image(session_id, filename):
    directory = USER_DATA_DIR / session_id
    if not (directory / filename).exists(): return "Image not found.", 404
    return send_from_directory(directory, filename)

@socketio.on('join')
def on_join(data):
    session_id = data['session_id']
    session = find_session_by_id(session_id)
    if session:
        # FIX 2: Store the client's unique connection ID (sid)
        session['sid'] = request.sid
        join_room(session_id)
        print(f"Client {request.sid} joined room: {session_id}")

@socketio.on('user_command')
def handle_user_command(data):
    session = find_session_by_id(data.get('session_id'))
    if not session: return
    command, value = data.get('command'), data.get('value')
    if command == 'message':
        if session.get("is_processing"):
            socketio.emit('session_update', {'log_message': {'sender':'ai', 'text':"Working... please Interrupt first."}}, room=session['id']); return
        session['is_processing'] = True
        session["chat_history"].append({"role": "user", "parts": [value]})
        socketio.start_background_task(process_next_browser_step, session, f"User Guidance: {value}")
    elif command == 'interrupt':
        session['interrupt_requested'] = True; session['is_processing'] = False
        socketio.emit('session_update', {'status': 'Interrupted. Ready for new command.'}, room=session['id'])
    elif command == 'stop':
        close_browser(session, reason="Session stopped by user via web interface.")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # (Webhook logic unchanged, but simplified here)
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN: return request.args.get('hub.challenge')
        return "Verification token mismatch", 403
    return "OK", 200

if __name__ == '__main__':
    print("--- Magic Clicky Server with Web UI & Live Control ---")
    socketio.run(app, host='0.0.0.0', port=5000)
