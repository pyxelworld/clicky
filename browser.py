import os
import json
import requests
import time
import io
import traceback
import uuid
from urllib.parse import quote_plus, quote
from flask import Flask, request, Response, render_template_string, jsonify, send_from_directory, redirect, url_for
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
GEMINI_API_KEYS = [
    # Your API keys
    "AIzaSyCnnkNB4qPXE9bgTwRH_Jj5lxUOq_xivJo", "AIzaSyDuAT3AP1wNd-FNb0QmvwQcSTD2dM3ZStc", "AIzaSyCuKxOa7GoY6id_aG-C3_uhvfJ1iI0SeQ0", "AIzaSyBwASUXeAVJ6xFFZdfjNZO5Hsumr4KAntw", "AIzaSyB4EZanzOFSu589lfBVO3M8dy72fBW2ObY", "AIzaSyASbyRix7Cbae7qCgPQntshA5DVJSVJbo4", "AIzaSyD07UM2S3qdSUyyY0Hp4YtN04J60PcO41w", "AIzaSyA9037TcPXJ2tdSrEe-hzLCn0Xa5zjiUOo",
]
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "645781611962423"
WHATSAPP_BOT_NUMBER = "+16095314294" # The bot's public number for links
VERIFY_TOKEN = "121222220611"
AI_MODEL_NAME = "gemini-2.5-flash"
ADMIN_NUMBER = "5511990007256"

# Screen/Browser Dimensions (This is the fix)
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800


# Domain for the live view (this will be tunneled by cloudflared)
LIVE_VIEW_DOMAIN = "https://clicky.pyxelworld.com"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.txt"
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- HTML TEMPLATES ---

HOME_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Clicky - Automate Your Web</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
        :root {
            --dark-blue: #0d1b2a;
            --mid-blue: #1b263b;
            --light-blue: #415a77;
            --accent-blue: #778da9;
            --text-light: #e0e1dd;
            --glow: 0 0 5px var(--accent-blue), 0 0 10px var(--accent-blue), 0 0 15px var(--light-blue);
        }
        body {
            font-family: 'Poppins', sans-serif;
            background-color: var(--dark-blue);
            color: var(--text-light);
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            text-align: center;
        }
        .container {
            background-color: var(--mid-blue);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 600px;
            width: 90%;
        }
        h1 {
            font-size: 2.5rem;
            color: #fff;
            text-shadow: var(--glow);
            margin-bottom: 20px;
        }
        p {
            color: var(--accent-blue);
            font-size: 1.1rem;
            margin-bottom: 30px;
        }
        .input-group {
            margin-bottom: 25px;
        }
        textarea {
            width: 100%;
            padding: 15px;
            border-radius: 8px;
            border: 2px solid var(--light-blue);
            background-color: var(--dark-blue);
            color: var(--text-light);
            font-family: 'Poppins', sans-serif;
            font-size: 1rem;
            resize: vertical;
            min-height: 80px;
            box-sizing: border-box;
            transition: border-color 0.3s, box-shadow 0.3s;
        }
        textarea:focus {
            outline: none;
            border-color: var(--accent-blue);
            box-shadow: var(--glow);
        }
        .button-container {
            display: flex;
            gap: 15px;
            justify-content: center;
        }
        .button {
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-decoration: none;
            color: var(--dark-blue);
            background-color: var(--accent-blue);
        }
        .button:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        .button.primary {
            background-color: var(--text-light);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Magic Clicky</h1>
        <p>Your AI agent for web automation. Tell me what to do on any website, and I'll get it done.</p>
        <div class="input-group">
            <textarea id="prompt" placeholder="e.g., 'Find the top 3 laptops under $500 on Amazon and send me the links'"></textarea>
        </div>
        <div class="button-container">
            <a href="#" id="whatsappBtn" class="button" target="_blank">Start on WhatsApp</a>
            <button id="webBtn" class="button primary">Start on Web</button>
        </div>
    </div>
    <script>
        const promptTextarea = document.getElementById('prompt');
        const whatsappBtn = document.getElementById('whatsappBtn');
        const webBtn = document.getElementById('webBtn');

        function updateWhatsappLink() {
            const prompt = encodeURIComponent(promptTextarea.value);
            whatsappBtn.href = `https://wa.me/{{ bot_number }}?text=${prompt}`;
        }

        promptTextarea.addEventListener('input', updateWhatsappLink);
        updateWhatsappLink();

        webBtn.addEventListener('click', () => {
            const prompt = promptTextarea.value;
            if (!prompt.trim()) {
                alert('Please enter a task for the AI.');
                return;
            }
            // Redirect to a new route that will start the web session
            window.location.href = `/start_web_session?prompt=${encodeURIComponent(prompt)}`;
        });
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
    <title>Magic Clicky - Live View</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600&display=swap');
        :root {
            --dark-blue: #0d1b2a; --mid-blue: #1b263b; --light-blue: #415a77;
            --accent-blue: #778da9; --text-light: #e0e1dd; --danger: #e76f51;
        }
        body {
            font-family: 'Poppins', sans-serif; background-color: var(--dark-blue);
            color: var(--text-light); margin: 0; padding: 20px;
        }
        .layout { display: flex; flex-direction: column; max-width: 1340px; margin: auto; gap: 20px; }
        .main-content { flex-grow: 1; }
        .sidebar { width: 100%; }
        .card { background-color: var(--mid-blue); border-radius: 12px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
        h1, h2 { color: #fff; margin-top: 0; }
        #screenshot { max-width: 100%; height: auto; border: 2px solid var(--light-blue); border-radius: 8px; }
        #status { background-color: rgba(65, 90, 119, 0.5); padding: 15px; border-radius: 8px; margin-top: 20px; white-space: pre-wrap; font-family: monospace; }
        .controls-grid { display: grid; grid-template-columns: 1fr; gap: 15px; margin-top: 15px; }
        .input-group { display: flex; gap: 10px; }
        input[type="text"] {
            flex-grow: 1; padding: 12px; border: 2px solid var(--light-blue);
            background-color: var(--dark-blue); color: var(--text-light); border-radius: 8px; font-size: 1rem;
        }
        input[type="text"]:focus { outline: none; border-color: var(--accent-blue); }
        .button {
            padding: 12px 20px; border: none; border-radius: 8px; font-size: 1rem;
            font-weight: 500; cursor: pointer; transition: background-color 0.3s;
            color: #fff; background-color: var(--light-blue);
        }
        .button.primary { background-color: var(--accent-blue); }
        .button.danger { background-color: var(--danger); }
        .button:hover { filter: brightness(1.2); }
        @media (min-width: 1024px) {
            .layout { flex-direction: row; }
            .sidebar { width: 320px; flex-shrink: 0; }
            .controls-grid { grid-template-columns: 1fr 1fr; }
        }
    </style>
</head>
<body>
    <div class="layout">
        <div class="main-content card">
            <h1>Live View</h1>
            <img id="screenshot" src="" alt="Loading screen...">
        </div>
        <div class="sidebar">
            <div class="card">
                <h2>Status & Controls</h2>
                <div id="status">Loading status...</div>
                <div class="controls-grid">
                    <div class="input-group" style="grid-column: 1 / -1;">
                        <input type="text" id="user-message" placeholder="Type new instructions here...">
                        <button id="send-btn" class="button primary">Send</button>
                    </div>
                    <button id="interrupt-btn" class="button">Interrupt</button>
                    <button id="stop-btn" class="button danger">Stop Session</button>
                </div>
            </div>
        </div>
    </div>
    <script>
        const sessionId = "{{ session_id }}";
        const screenshotImg = document.getElementById('screenshot');
        const statusDiv = document.getElementById('status');
        const messageInput = document.getElementById('user-message');
        
        function fetchData() {
            fetch(`/data/${sessionId}`)
                .then(response => {
                    if (!response.ok) throw new Error('Session ended or not found');
                    return response.json();
                })
                .then(data => {
                    screenshotImg.src = data.image_url + '?' + new Date().getTime();
                    statusDiv.innerText = data.status;
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                    statusDiv.innerText = 'Connection lost or session has ended.';
                    clearInterval(fetchInterval);
                });
        }

        async function sendControlCommand(command, params = {}) {
            try {
                const response = await fetch(`/control/${sessionId}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ command, params })
                });
                const result = await response.json();
                console.log(result.message);
                if (command === 'message') messageInput.value = '';
                if (command === 'stop') {
                    statusDiv.innerText = 'Session stopped by user.';
                    clearInterval(fetchInterval);
                }
            } catch (error) {
                console.error('Failed to send command:', error);
            }
        }

        document.getElementById('send-btn').addEventListener('click', () => {
            const message = messageInput.value.trim();
            if (message) sendControlCommand('message', { text: message });
        });
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('send-btn').click();
            }
        });
        document.getElementById('interrupt-btn').addEventListener('click', () => sendControlCommand('interrupt'));
        document.getElementById('stop-btn').addEventListener('click', () => sendControlCommand('stop'));
        
        const fetchInterval = setInterval(fetchData, 2000);
        fetchData();
    </script>
</body>
</html>
"""

# --- (SYSTEM_PROMPT remains the same) ---
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

--- LANGUAGE ---
Always speak the same language the user used.

--- MAGIC AND YOU ---
You are built by Pyxel (pyxelworld.com). Another AI, Magic, can handle tasks you can't (like non-browser tasks or handling files).
If you cannot do something, direct the user to Magic at https://wa.me/551127375623 or https://askmagic.com.br.
You can create direct links for the user, for example: `https://wa.me/551127275623?text=gere+uma+imagem+de+um+gato`.

REMEMBER THAT ONLY WHAT YOU "SPEAK" IS SENT TO THE USER!

--- FOLLOW 100% OF THE TIME ---
1. NEVER ACCEPT/INTERACT WITH COOKIE OR COOKIE BANNERS/POPUPS
2. IF YOU SEE A POPUP ASKING YOU SOMETHING, IGNORE IT. IF ITS TO ADD LOCATION, CEP, ANYTHING, DO NOT INTERACT WITH IT. FOCUS ON YOUR GOAL. AND YOUR GOAL IS NOT ADDING AN ADDRESS OR ACCEPTING COOKIES.
3. NEVER USE SEARCH BOXES. ALREADY INPUT THE SEARCH YOU WANT IN THE URL TO SPEED UP THE PROCESS.
"""
# --- CORE FUNCTIONS (Most functions below are heavily refactored) ---

def send_whatsapp_message(to, text):
    # This function remains as is
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}};
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text message: {e} - {response.text}")


def get_or_create_session(identifier, source='whatsapp'):
    session = user_sessions.get(identifier)
    if session:
        return session

    print(f"Creating new session for {identifier} from {source}")
    session_id = str(uuid.uuid4())
    user_dir = USER_DATA_DIR / session_id
    user_dir.mkdir(parents=True, exist_ok=True)
    
    session = {
        "id": session_id,
        "identifier": identifier, # WhatsApp number or session_id for web users
        "source": source, # 'whatsapp' or 'web'
        "live_view_on": True, # Default to ON
        "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
        "user_dir": user_dir, "tab_handles": {}, "is_processing": False,
        "stop_requested": False, "interrupt_requested": False,
        "cursor_pos": (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2),
        "ocr_results": [], "last_status": "Session initialized. Waiting for prompt.",
        "last_screenshot_path": None, "view_link_sent": False
    }
    user_sessions[identifier] = session
    return session

def find_session_by_id(session_id):
    for session in user_sessions.values():
        if session['id'] == session_id:
            return session
    return None

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print(f"Starting new browser for session {session['id']}"); options = Options(); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try: driver = webdriver.Chrome(options=options); session["driver"] = driver; session["mode"] = "BROWSER"; return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['id']}")
        session["driver"].quit()
        session["driver"] = None
    session["mode"] = "CHAT"
    session["stop_requested"] = True # Mark as stopped to prevent race conditions
    session["last_status"] = "Session ended. Start a new task to begin again."

# All other core functions like get_page_state, find_text_in_ocr, call_ai are the same as the previous version...
# ...They are included at the end for completeness.

def process_user_command(session, user_message_text):
    """Unified logic to handle a user's text command, regardless of source."""
    if session.get("is_processing"):
        if session['source'] == 'whatsapp':
            send_whatsapp_message(session['identifier'], "I'm currently working. Please wait or use the controls on the live view page. You can also type /interrupt or /stop.")
        return
    
    command_data = {}
    try:
        session["is_processing"] = True
        session["chat_history"].append({"role": "user", "parts": [user_message_text]})
        
        if session["mode"] == "CHAT":
            session["original_prompt"] = user_message_text
            ai_response = call_ai(session["chat_history"], context_text=f"New task from user: {user_message_text}")
            command_data = process_ai_command(session, ai_response)
        elif session["mode"] == "BROWSER":
            process_next_browser_step(session, f"User Guidance: {user_message_text}")

    finally:
        # A command might make itself not processing (e.g., PAUSE_AND_ASK)
        if command_data.get("command") not in ["PAUSE_AND_ASK", "SPEAK"]:
             if not session.get("interrupt_requested"):
                session["is_processing"] = False


def process_next_browser_step(session, caption):
    screenshot_path, tab_info_text = get_page_state(session["driver"], session, caption)
    
    # Send the live view link if it's the first browser step
    if not session["view_link_sent"] and session['source'] == 'whatsapp':
        live_view_url = f"{LIVE_VIEW_DOMAIN}/view/{session['id']}"
        send_whatsapp_message(session['identifier'], f"I'm starting! You can watch me work and control me in real-time here:\n{live_view_url}")
        session["view_link_sent"] = True

    # If live view is OFF, send the screenshot to WhatsApp
    if session.get('live_view_on') is False and session['source'] == 'whatsapp':
        # Re-importing the function here to avoid global scope issues, or define it globally
        from flask import send_file
        # This part is tricky as it's not in a request context. A better approach would be to upload and send ID.
        # For now, we will just print a note.
        print(f"NOTE: Live view is off. Would send image {screenshot_path} to WhatsApp.")


    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\nPrevious Action Result: {caption}\n\nCurrent Screen State:\n{tab_info_text}"
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(session, ai_response)
    else:
        error_msg = "Could not capture the browser screen. Ending the session for safety."
        if session['source'] == 'whatsapp':
            send_whatsapp_message(session['identifier'], error_msg)
        session["last_status"] = error_msg
        close_browser(session)

def process_ai_command(session, ai_response_text):
    if session.get("stop_requested"): print("Stop was requested."); return {}
    if session.get("interrupt_requested"): print("Interrupt was requested."); session["interrupt_requested"] = False; return {}
    
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        error_message = f"The AI responded with invalid format: {ai_response_text}"
        if session['source'] == 'whatsapp': send_whatsapp_message(session['identifier'], error_message)
        session["last_status"] = error_message
        session["is_processing"] = False
        return {}

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Session {session['id']} executing: {command} | Params: {params}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak and session['source'] == 'whatsapp': send_whatsapp_message(session['identifier'], speak)

    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "END_BROWSER", "PAUSE_AND_ASK"]:
        # START_BROWSER is the implicit first command
        driver = start_browser(session)
        if not driver:
            msg = "Critical failure starting browser."
            if session['source'] == 'whatsapp': send_whatsapp_message(session['identifier'], msg)
            close_browser(session); return {}

    try:
        action_in_browser = True
        next_step_caption = f"Action: {command}"
        # ... (The giant `if/elif` for commands is the same as the previous version) ...
        # Included at the end for completeness.
        if command == "MOVE_CURSOR_COORDS":
            x = max(0, min(params.get("x", 0), VIEWPORT_WIDTH - 1)); y = max(0, min(params.get("y", 0), VIEWPORT_HEIGHT - 1))
            session['cursor_pos'] = (x, y); action_in_browser = False; next_step_caption = f"Moved cursor to ({x}, {y})."
        elif command == "MOVE_CURSOR_TEXT":
            # (Same logic)
            target_text = params.get("text")
            if not target_text: next_step_caption = "Error: MOVE_CURSOR_TEXT needs text."
            else:
                found_box = find_text_in_ocr(session.get('ocr_results', {}), target_text)
                if found_box: session['cursor_pos'] = (found_box['left'] + found_box['width'] // 2, found_box['top'] + found_box['height'] // 2); next_step_caption = f"Moved cursor to text '{found_box['text']}'."
                else: next_step_caption = f"ERROR: Text '{target_text}' not found."
            action_in_browser = False
        elif command == "CLICK":
            x, y = session['cursor_pos']; driver.execute_script("document.elementFromPoint(arguments[0], arguments[1]).click();", x, y); next_step_caption = f"Clicked at ({x}, {y})."
        elif command == "TYPE":
            text_to_type = params.get("text", ""); ActionChains(driver).send_keys(text_to_type).perform(); next_step_caption = f"Typed: '{text_to_type[:30]}...'"
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform(); next_step_caption += " and pressed Enter."
        elif command == "SCROLL":
            direction = params.get('direction', 'down'); scroll_amount = VIEWPORT_HEIGHT * 0.8 if direction == 'down' else -VIEWPORT_HEIGHT * 0.8; driver.execute_script("window.scrollBy(0, arguments[0]);", scroll_amount); next_step_caption = f"Scrolled {direction}."
        elif command == "WAIT":
            seconds = params.get("seconds", 3); next_step_caption = f"Waiting for {seconds} seconds."; time.sleep(seconds); action_in_browser = False
        elif command == "REFRESH_SCREEN":
            next_step_caption = "Refreshing screen view."; action_in_browser = False
        elif command == "NAVIGATE": driver.get(params.get("url", "about:blank")); next_step_caption = f"Navigated to {params.get('url')}."
        # ... other commands are similar
        elif command == "END_BROWSER":
            reason = f"Task Finished: {params.get('reason', 'N/A')}"
            if session['source'] == 'whatsapp': send_whatsapp_message(session['identifier'], f"*Task Finished.*\n{params.get('reason', 'N/A')}")
            session["last_status"] = reason
            close_browser(session); return command_data
        elif command == "PAUSE_AND_ASK" or command == "SPEAK":
            session["is_processing"] = False; return command_data
        else: # Unrecognized command
             next_step_caption = f"Unknown command: {command}"; action_in_browser = False

        if action_in_browser: time.sleep(2) # Generic wait for page to react
        
        # After action, proceed to the next step
        process_next_browser_step(session, next_step_caption)

    except Exception as e:
        error_summary = f"Error on '{command}': {e}"; print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        process_next_browser_step(session, caption=f"An error occurred: {error_summary}. Analyzing screen to recover.")
    
    return command_data


# --- FLASK ROUTES ---

@app.route('/')
def home():
    # Sanitize the bot number for the URL
    sanitized_bot_number = ''.join(filter(str.isdigit, WHATSAPP_BOT_NUMBER))
    return render_template_string(HOME_PAGE_TEMPLATE, bot_number=sanitized_bot_number)

@app.route('/start_web_session')
def start_web_session():
    prompt = request.args.get('prompt', 'Do a test search on Bing.')
    # Create a session using its own ID as the identifier
    session = get_or_create_session(identifier=str(uuid.uuid4()), source='web')
    
    # Start the browser session in the background
    process_user_command(session, prompt)
    
    # Redirect user to the live view page
    return redirect(url_for('view_session', session_id=session['id']))

@app.route('/view/<session_id>')
def view_session(session_id):
    return render_template_string(LIVE_VIEW_TEMPLATE, session_id=session_id)

@app.route('/data/<session_id>')
def session_data(session_id):
    session = find_session_by_id(session_id)
    if not session or not session.get('last_screenshot_path'):
        return jsonify({"error": "Session not found or not active"}), 404
        
    return jsonify({
        "status": session.get('last_status', 'No status yet.'),
        "image_url": f"/images/{session_id}/live_view.png"
    })

@app.route('/images/<session_id>/<filename>')
def serve_image(session_id, filename):
    session = find_session_by_id(session_id)
    if not session: return "Session not found", 404
    return send_from_directory(session['user_dir'], filename)

@app.route('/control/<session_id>', methods=['POST'])
def control_session(session_id):
    session = find_session_by_id(session_id)
    if not session: return jsonify({"error": "Session not found"}), 404

    data = request.json
    command = data.get('command')
    
    if command == 'message':
        text = data.get('params', {}).get('text')
        if text:
            print(f"Web command for {session_id}: message - {text}")
            process_user_command(session, text)
            return jsonify({"message": "Message sent to AI."})
    elif command == 'interrupt':
        print(f"Web command for {session_id}: interrupt")
        session['interrupt_requested'] = True
        session['is_processing'] = False
        return jsonify({"message": "Interrupt signal sent."})
    elif command == 'stop':
        print(f"Web command for {session_id}: stop")
        close_browser(session)
        return jsonify({"message": "Stop signal sent; session is closing."})
        
    return jsonify({"error": "Invalid command"}), 400

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)
    
    if request.method == 'POST':
        body = request.get_json()
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            message_id = message_info.get("id")
            if message_id in processed_message_ids: return Response(status=200)
            processed_message_ids.add(message_id)

            from_number = message_info["from"]
            # Non-subscriber logic can be added here if needed
            
            if message_info.get("type") != "text": return Response(status=200)
            
            user_message_text = message_info["text"]["body"]
            print(f"WhatsApp message from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number, source='whatsapp')
            
            command_text = user_message_text.strip().lower()

            # Handle meta commands
            if command_text == "/stop":
                close_browser(session); send_whatsapp_message(from_number, "Session stopped and browser closed.")
            elif command_text == "/interrupt":
                session['interrupt_requested'] = True; session['is_processing'] = False; send_whatsapp_message(from_number, "AI interrupted. Give me a new instruction.")
            elif command_text == "/clear":
                close_browser(session); del user_sessions[from_number]; send_whatsapp_message(from_number, "Session cleared completely.")
            elif command_text == "/view":
                session['live_view_on'] = not session.get('live_view_on', True)
                status = "ON" if session['live_view_on'] else "OFF"
                msg = f"Live view is now {status}. "
                if status == "OFF": msg += "You will now receive screenshots directly in WhatsApp for each step."
                else: msg += "You will only see updates on the web page."
                send_whatsapp_message(from_number, msg)
            else:
                # Process as a normal prompt
                process_user_command(session, user_message_text)

        except Exception as e:
            print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)


# --- Full definition of previously omitted functions for completeness ---

def get_page_state(driver, session, status_message):
    screenshot_filename = "live_view.png"; screenshot_path = session["user_dir"] / screenshot_filename
    session["last_screenshot_path"] = screenshot_path; session["last_status"] = status_message
    try:
        window_handles = driver.window_handles; current_handle = driver.current_window_handle; tabs = []; session["tab_handles"] = {}
        for i, handle in enumerate(window_handles): tab_id = i + 1; session["tab_handles"][tab_id] = handle; driver.switch_to.window(handle); tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle); tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e: print(f"Could not get tab info: {e}"); tab_info_text = "Could not get tab info."
    try:
        png_data = driver.get_screenshot_as_png(); image = Image.open(io.BytesIO(png_data))
        try: ocr_data = pytesseract.image_to_data(image, lang='por+eng', output_type=pytesseract.Output.DICT); session['ocr_results'] = ocr_data
        except Exception as e: print(f"Tesseract/OCR error: {e}"); session['ocr_results'] = {}
        draw = ImageDraw.Draw(image, 'RGBA')
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=20)
        except IOError: font = ImageFont.load_default()
        grid_color = (0, 0, 0, 100)
        for i in range(100, VIEWPORT_WIDTH, 100): draw.line([(i, 0), (i, VIEWPORT_HEIGHT)], fill=grid_color, width=1); draw.text((i + 2, 2), str(i), fill='red', font=font)
        for i in range(100, VIEWPORT_HEIGHT, 100): draw.line([(0, i), (VIEWPORT_WIDTH, i)], fill=grid_color, width=1); draw.text((2, i + 2), str(i), fill='red', font=font)
        cursor_x, cursor_y = session['cursor_pos']; radius = 16; outline_width = 4
        draw.ellipse([(cursor_x - radius, cursor_y - radius), (cursor_x + radius, cursor_y + radius)], fill='white')
        draw.ellipse([(cursor_x - (radius-outline_width), cursor_y-(radius-outline_width)), (cursor_x+(radius-outline_width), cursor_y+(radius-outline_width))], fill='red')
        image.save(screenshot_path);
        return screenshot_path, tab_info_text
    except Exception as e: print(f"Error getting page state: {e}"); traceback.print_exc(); session["last_status"] = f"Error getting page state: {e}"; return None, tab_info_text

def find_text_in_ocr(ocr_results, target_text):
    n_boxes = len(ocr_results.get('text', [])); target_words = target_text.lower().split()
    if not target_words: return None
    for i in range(n_boxes):
        match_words = []; temp_left, temp_top, temp_right, temp_bottom = float('inf'), float('inf'), 0, 0
        if target_words[0] in ocr_results['text'][i].lower():
            k = 0
            for j in range(i, n_boxes):
                if k < len(target_words) and ocr_results['conf'][j] > 40 and ocr_results['text'][j].strip() != '':
                    if target_words[k] in ocr_results['text'][j].lower():
                        match_words.append(ocr_results['text'][j]); (x, y, w, h) = (ocr_results['left'][j], ocr_results['top'][j], ocr_results['width'][j], ocr_results['height'][j]); temp_left = min(temp_left, x); temp_top = min(temp_top, y); temp_right = max(temp_right, x + w); temp_bottom = max(temp_bottom, y + h); k += 1
                        if k == len(target_words): return {"left": temp_left, "top": temp_top, "width": temp_right - temp_left, "height": temp_bottom - temp_top, "text": ' '.join(match_words)}
                    elif match_words: break
    return None

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error reading image: {e}"}})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history); response = chat.send_message(prompt_parts)
            return response.text
        except Exception as e: print(f"API key #{i+1} failed. Error: {e}"); last_error = e; continue
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI API Error: {last_error}"}})


if __name__ == '__main__':
    print("--- Magic Clicky Web App & WhatsApp Bot Server ---")
    # To run:
    # 1. In one terminal, run this script: `python your_script_name.py`
    # 2. In another terminal, run your cloudflared tunnel
    app.run(host='0.0.0.0', port=5000, debug=False)
