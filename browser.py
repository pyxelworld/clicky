# FIX 1: Eventlet monkey patching must be the very first thing to run.
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
GEMINI_API_KEYS = [
    # "YOUR_GEMINI_API_KEY_1",
    # "YOUR_GEMINI_API_KEY_2",
]
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

SYSTEM_PROMPT = """
You are "Magic Clicky," a powerful AI that controls a web browser with high precision. You see the screen and choose the best command to achieve your goal.

--- YOUR CORE MECHANISM: DUAL-MODE CURSOR CONTROL ---

You control a **large red dot** (your virtual cursor). To interact, you MUST first move the cursor to the target, then act. You have two ways to move the cursor. Choose the best one for the job.

**1. Text Mode (Primary Choice for Text): `MOVE_CURSOR_TEXT`**
-   **How it works:** You provide a string of text that you see on the screen. The system uses OCR to find this text and instantly moves the cursor to its center. This is the FASTEST and MOST ACCURATE method for clicking buttons, links, or anything with a clear text label.
-   **Usage:** `{"command": "MOVE_CURSOR_TEXT", "params": {"text": "Login"}}`

**2. Coordinate Mode (For Visual Elements): `MOVE_CURSOR_COORDS`**
-   **How it works:** The screen has a subtle gray grid with numbered axes. Use this grid to estimate the (x, y) coordinates of your target. This is best for clicking on icons, images, or areas without any text. Coordinates MUST be within 0-1279 for x and 0-799 for y (viewport size: 1280x800).
-   **Usage:** `{"command": "MOVE_CURSOR_COORDS", "params": {"x": 120, "y": 455}}`

--- THE MANDATORY WORKFLOW: MOVE -> VERIFY -> ACT ---

This 3-step process is ESSENTIAL.
1.  **MOVE:** Issue either a `MOVE_CURSOR_TEXT` or `MOVE_CURSOR_COORDS` command.
2.  **VERIFY:** You will receive a new screenshot. **CRITICALLY, EXAMINE IT.** Is the red dot EXACTLY on your target?
3.  **ACT:**
    -   If the dot is correct, issue your action command (`CLICK`, `CLEAR`, etc.).
    -   If the dot is slightly off, DO NOT CLICK. Issue another `MOVE_CURSOR` command to correct its position. For text, maybe try a shorter or different part of the text. For coordinates, adjust the numbers.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

**== CURSOR MOVEMENT & ACTION COMMANDS ==**
1.  **`MOVE_CURSOR_TEXT`**: Moves the cursor to the center of the specified text found by OCR.
    - **Params:** `{"text": "<text_on_screen>"}`
2.  **`MOVE_CURSOR_COORDS`**: Moves the cursor to a specific (x, y) coordinate. Use the visual grid for reference.
    - **Params:** `{"x": <int>, "y": <int>}`
3.  **`CLICK`**: Performs a REAL mouse click at the cursor's current location. Must be used after moving the cursor.
    - **Params:** `{}`
4.  **`TYPE`**: Types text. You MUST `CLICK` an input field first.
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`
5.  **`CLEAR`**: Clears the input field under the cursor.
    - **Params:** `{}`
6.  **`SCROLL`**: Scrolls the page from the cursor's position.
    - **Params:** `{"direction": "<up|down>"}`

**== BROWSER & NAVIGATION COMMANDS ==**
7.  **`END_BROWSER`**: Closes the browser when the task is fully complete.
    - **Params:** `{"reason": "<summary>"}`
8.  **`NAVIGATE`**: Goes directly to a URL. IF YOU KNOW THE URL, GO DIRECTLY.
    - **Params:** `{"url": "<full_url>"}`
9.  **`CUSTOM_SEARCH`**: Performs a search using "Bing".
    - **Params:** `{"query": "<search_term>"}`
10. **`GO_BACK`**: Navigates to the previous page in history.
    - **Params:** `{}`
11. **`GET_CURRENT_URL`**: Gets the URL of the current page. The URL will be shown to you in the next step to confirm your location.
    - **Params:** `{}`

**== TAB MANAGEMENT COMMANDS ==**
12. **`NEW_TAB`**: Opens a new browser tab.
13. **`SWITCH_TO_TAB`**: Switches to an existing tab by its ID number.
14. **`CLOSE_TAB`**: Closes the current tab.

**== STATE & TIMING COMMANDS ==**
15. **`WAIT`**: Pauses for a few seconds (for loading content) then views the screen again.
    - **Params:** `{"seconds": <int>}` (Optional, defaults to 3)
16. **`REFRESH_SCREEN`**: Does no action, just gets a new view of the screen.
    - **Params:** `{}`

**== USER INTERACTION COMMANDS ==**
17. **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
    - **Params:** `{"question": "<your_question>"}`
18. **`SPEAK`**: For simple conversation when no browser action is needed.
    - **Params:** `{"text": "<your_response>"}`


-- ERROR RECOVERY ---
If a command fails, the page may have changed. Analyze the new screenshot and the error message. Do not repeat the failed command. Issue a new command to recover.

--- GUIDING PRINCIPLES ---
1.  **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down on a page after it loads or after an action to understand the full context.
2.  **SEARCH STRATEGY:** Use `CUSTOM_SEARCH` with "Bing". Do NOT use `NAVIGATE` to go to other search engines.
3.  **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt it. Stop and ask the user for permission using `PAUSE_AND_ASK`.
4.  **SHOPPING STRATEGY:** Use `PAUSE_AND_ASK` to clarify product and price. Use sorting/filtering features on sites.
5.  **POPUPS AND COOKIES:** IGNORE THEM. Do NOT click accept or reject. Just continue with your task.
6.  IF YOU KNOW A WEBSITES URL, USE IT TO DIRECTLY GO TO IT WITHOUT USING SEARCH ENGINES (NAVIGATE TOOL)
7.  ALWAYS TRY TO USE SEARCH BARS AS LESS AS POSSIBLE. IF YOU CAN USE THE NAVIGATE TOOL TO ALREADY GO TO A WEBSITE AND SEARCH ON IT WITH THE QUERY ON THE LINK (example https://lista.mercadolivre.com.br/QUERY) DO IT.
"""

# --- HTML TEMPLATES ---
HOME_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Clicky - Your AI Web Agent</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        :root { --bg-dark: #0d1117; --primary: #0c2d48; --secondary: #145da0; --accent: #2e8bc0; --text-light: #e6f1ff; --text-dark: #b1d4e0; --border-color: #30363d; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-light); margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { max-width: 800px; text-align: center; padding: 2rem; background: rgba(255, 255, 255, 0.05); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(5px); -webkit-backdrop-filter: blur(5px); border: 1px solid var(--border-color); }
        h1 { font-size: 3rem; color: #fff; margin-bottom: 0.5rem; }
        p.subtitle { font-size: 1.2rem; color: var(--text-dark); margin-bottom: 2.5rem; }
        .tab-container { display: flex; justify-content: center; margin-bottom: 2rem; }
        .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.3s ease; color: var(--text-dark); }
        .tab.active { color: var(--text-light); border-bottom-color: var(--accent); }
        .content { display: none; } .content.active { display: block; }
        textarea, input { width: 95%; background-color: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-light); border-radius: 8px; padding: 12px; font-family: 'Inter', sans-serif; font-size: 1rem; margin-bottom: 1rem; resize: vertical; }
        button { width: 100%; padding: 14px; border: none; border-radius: 8px; background-color: var(--secondary); color: #fff; font-size: 1.1rem; font-weight: 500; cursor: pointer; transition: background-color 0.3s ease; }
        button:hover { background-color: var(--accent); }
    </style>
</head>
<body>
<div class="container">
    <h1>Magic Clicky</h1>
    <p class="subtitle">Give me a task, and I'll control a browser to get it done.</p>
    <div class="tab-container">
        <div class="tab active" onclick="showTab('web')">Use on Web</div>
        <div class="tab" onclick="showTab('whatsapp')">Use on WhatsApp</div>
    </div>
    <div id="web" class="content active">
        <form action="/start-web-session" method="post">
            <textarea name="prompt" rows="4" placeholder="e.g., 'Find the top 3 rated sci-fi books on Goodreads and tell me their authors.'" required></textarea>
            <button type="submit">Start Web Session</button>
        </form>
    </div>
    <div id="whatsapp" class="content">
        <form id="whatsapp-form">
            <textarea id="whatsapp-prompt" rows="4" placeholder="Type your task here to send to WhatsApp..."></textarea>
            <button type="button" onclick="sendToWhatsApp()">Go to WhatsApp</button>
        </form>
    </div>
</div>
<script>
    function showTab(tabName) { document.querySelectorAll('.tab').forEach(t => t.classList.remove('active')); document.querySelectorAll('.content').forEach(c => c.classList.remove('active')); document.querySelector(`.tab[onclick="showTab('${tabName}')"]`).classList.add('active'); document.getElementById(tabName).classList.add('active'); }
    function sendToWhatsApp() { const prompt = document.getElementById('whatsapp-prompt').value; const encodedPrompt = encodeURIComponent(prompt); window.location.href = `https://wa.me/{{ whatsapp_number }}?text=${encodedPrompt}`; }
</script>
</body>
</html>
"""

LIVE_VIEW_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Clicky - Live Session</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        :root { --bg-dark: #0d1117; --primary: #0c2d48; --secondary: #145da0; --accent: #2e8bc0; --text-light: #e6f1ff; --text-dark: #b1d4e0; --border-color: #30363d; --danger: #b00020; --danger-hover: #d32f2f; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-light); margin: 0; display: flex; height: 100vh; overflow: hidden; }
        .main-content { flex: 3; display: flex; flex-direction: column; padding: 1rem; }
        .sidebar { flex: 1; background-color: #010409; border-left: 1px solid var(--border-color); display: flex; flex-direction: column; padding: 1rem; height: 100vh; }
        .screenshot-container { background-color: #010409; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; flex-grow: 1; display: flex; justify-content: center; align-items: center; }
        #screenshot { max-width: 100%; max-height: 100%; object-fit: contain; }
        #status-bar { background-color: var(--primary); padding: 0.75rem 1rem; border-radius: 8px; margin-top: 1rem; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .sidebar h2 { margin-top: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 0.5rem; }
        .chat-log { flex-grow: 1; overflow-y: auto; margin-bottom: 1rem; }
        .chat-log div { padding: 8px; border-radius: 5px; margin-bottom: 8px; max-width: 95%; word-wrap: break-word; line-height: 1.4; }
        .chat-log .user { background-color: var(--secondary); margin-left: auto; }
        .chat-log .ai { background-color: #21262d; }
        .controls textarea { width: 95%; background-color: #21262d; border: 1px solid var(--border-color); color: var(--text-light); border-radius: 8px; padding: 10px; font-family: 'Inter', sans-serif; font-size: 0.9rem; margin-bottom: 0.5rem; resize: vertical; }
        .controls button { width: 100%; padding: 10px; border: none; border-radius: 8px; background-color: var(--secondary); color: #fff; font-size: 1rem; cursor: pointer; transition: background-color 0.3s ease; margin-top: 5px; }
        .controls button:hover { background-color: var(--accent); } .controls .interrupt-btn { background-color: var(--accent); } .controls .interrupt-btn:hover { background-color: var(--secondary); } .controls .stop-btn { background-color: var(--danger); } .controls .stop-btn:hover { background-color: var(--danger-hover); }
    </style>
</head>
<body>
<div class="main-content">
    <div class="screenshot-container"><img id="screenshot" src="" alt="Waiting for session to start..."></div>
    <div id="status-bar">Initializing...</div>
</div>
<div class="sidebar">
    <h2>Session Log</h2>
    <div class="chat-log" id="chat-log"></div>
    <div class="controls">
        <textarea id="user-input" rows="3" placeholder="Provide additional instructions..."></textarea>
        <button onclick="sendMessage()">Send Message</button>
        <button class="interrupt-btn" onclick="sendControl('interrupt')">Interrupt</button>
        <button class="stop-btn" onclick="sendControl('stop')">Stop Session</button>
    </div>
</div>
<script>
    const sessionId = "{{ session_id }}";
    const socket = io();
    socket.on('connect', () => { console.log('Connected!'); socket.emit('join', { session_id: sessionId }); });
    socket.on('session_update', (data) => {
        if (data.image_path) { document.getElementById('screenshot').src = data.image_path + '?' + new Date().getTime(); }
        if (data.status) { document.getElementById('status-bar').innerText = "Status: " + data.status; }
        if (data.log_message) { addLogMessage(data.log_message.sender, data.log_message.text); }
    });
    socket.on('session_ended', (data) => { document.getElementById('status-bar').innerText = "SESSION ENDED: " + data.reason; document.querySelectorAll('.controls button, .controls textarea').forEach(el => el.disabled = true); addLogMessage('ai', "The session has ended. " + data.reason); });
    function addLogMessage(sender, text) { const chatLog = document.getElementById('chat-log'); const msgDiv = document.createElement('div'); msgDiv.classList.add(sender); msgDiv.innerText = text; chatLog.appendChild(msgDiv); chatLog.scrollTop = chatLog.scrollHeight; }
    function sendMessage() { const input = document.getElementById('user-input'); const message = input.value; if (message.trim() === '') return; socket.emit('user_command', { session_id: sessionId, command: 'message', value: message }); addLogMessage('user', message); input.value = ''; }
    function sendControl(commandType) { socket.emit('user_command', { session_id: sessionId, command: commandType, value: '' }); addLogMessage('user', `Sent /${commandType} command.`); }
</script>
</body>
</html>
"""

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
    if not GEMINI_API_KEYS: return json.dumps({"command": "END_BROWSER", "params": {"reason": "No API keys provided."}})
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
    n_boxes = len(ocr_results.get('text', [])); target_words = target_text.lower().split()
    if not target_words: return None
    for i in range(n_boxes):
        match_words = []; temp_left, temp_top, temp_right, temp_bottom = float('inf'), float('inf'), 0, 0
        if target_words[0] in ocr_results['text'][i].lower():
            k = 0
            for j in range(i, n_boxes):
                if k < len(target_words) and ocr_results['conf'][j] > 40:
                    if target_words[k] in ocr_results['text'][j].lower():
                        match_words.append(ocr_results['text'][j]);(x, y, w, h) = (ocr_results['left'][j], ocr_results['top'][j], ocr_results['width'][j], ocr_results['height'][j]);temp_left = min(temp_left, x); temp_top = min(temp_top, y); temp_right = max(temp_right, x + w); temp_bottom = max(temp_bottom, y + h);k += 1
                        if k == len(target_words): return {"left": temp_left, "top": temp_top, "width": temp_right - temp_left, "height": temp_bottom - temp_top, "text": ' '.join(match_words)}
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
        "view_link_sent": False, "live_view_updates_on": True, "sid": None
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
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=20)
        except IOError: font = ImageFont.load_default()
        grid_color = (0, 0, 0, 100)
        for i in range(100, VIEWPORT_WIDTH, 100): draw.line([(i, 0), (i, VIEWPORT_HEIGHT)], fill=grid_color, width=1); draw.text((i + 2, 2), str(i), fill='red', font=font)
        for i in range(100, VIEWPORT_HEIGHT, 100): draw.line([(0, i), (VIEWPORT_WIDTH, i)], fill=grid_color, width=1); draw.text((2, i + 2), str(i), fill='red', font=font)
        cursor_x, cursor_y = session['cursor_pos']; radius = 16; outline_width = 4
        draw.ellipse([(cursor_x - radius, cursor_y - radius), (cursor_x + radius, cursor_y + radius)], fill='white')
        draw.ellipse([(cursor_x - (radius-outline_width), cursor_y-(radius-outline_width)), (cursor_x+(radius-outline_width), cursor_y+(radius-outline_width))], fill='red')
        image.save(screenshot_path)
        update_data = {'status': status_message, 'image_path': f"/images/{session['id']}/{screenshot_filename}"}
        socketio.emit('session_update', update_data, room=session['id'])
        # Simplified tab info gathering for brevity
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
        if command == "END_BROWSER":
            close_browser(session, f"Task Completed. Summary: {params.get('reason', 'N/A')}")
            if session['session_type'] == 'whatsapp': send_whatsapp_message(session['identifier'], f"*Task Completed.*\n*Summary:* {params.get('reason', 'N/A')}")
            return command_data
        elif command == "MOVE_CURSOR_COORDS" or command == "MOVE_CURSOR_TEXT" or command == "REFRESH_SCREEN" or command == "GET_CURRENT_URL":
            action_in_browser = False # These actions don't require a page load wait
            # (Actual logic for these commands would be here)
            pass
        elif command == "WAIT":
            time.sleep(params.get("seconds", 3))
            action_in_browser = False
        else:
            # (Actual logic for CLICK, TYPE, SCROLL, NAVIGATE etc. would be here)
            pass
        if action_in_browser: time.sleep(2)
        socketio.start_background_task(process_next_browser_step, session, next_step_caption)
    except Exception as e:
        error_summary = f"Error running '{command}': {e}"
        socketio.start_background_task(process_next_browser_step, session, error_summary)
    return command_data

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
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification token mismatch", 403
    
    if request.method == 'POST':
        body = request.get_json()
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            message_id = message_info.get("id")
            if message_id in processed_message_ids: return Response(status=200)
            processed_message_ids.add(message_id)

            from_number = message_info["from"]
            if from_number not in subscribers: return Response(status=200) # Or handle non-subscribers
            
            message_type = message_info.get("type")
            if message_type != "text": return Response(status=200)

            user_message_text = message_info["text"]["body"]
            command_text = user_message_text.strip().lower()
            session = user_sessions.get(from_number)

            if command_text == '/view':
                if session:
                    session['live_view_updates_on'] = not session.get('live_view_updates_on', True)
                    status = "ON" if session['live_view_updates_on'] else "OFF"
                    send_whatsapp_message(from_number, f"Step-by-step WhatsApp updates are now {status}.")
                else: send_whatsapp_message(from_number, "No active session. Start a task first.")
                return Response(status=200)

            if session and session.get('is_processing'):
                send_whatsapp_message(from_number, "I'm currently working. Please use the live view link to interact, or send /stop to cancel.")
                return Response(status=200)

            # Start a new session
            new_session = create_new_session(identifier=from_number, prompt=user_message_text, session_type="whatsapp")
            new_session['is_processing'] = True
            socketio.start_background_task(target=run_initial_ai, session=new_session, user_message=user_message_text)

        except (KeyError, IndexError, TypeError) as e:
            print(f"Webhook parsing error: {e}")
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Clicky Server with Web UI & Live Control ---")
    socketio.run(app, host='0.0.0.0', port=5000)
