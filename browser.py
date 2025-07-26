import os
import json
import requests
import time
import io
import traceback
import uuid
from urllib.parse import quote_plus, urlencode
from flask import Flask, request, Response, render_template_string, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO # ## NEW ##
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
]
WHATSAPP_TOKEN = "YOUR_WHATSAPP_TOKEN"
WHATSAPP_PHONE_NUMBER_ID = "YOUR_PHONE_NUMBER_ID"
VERIFY_TOKEN = "YOUR_VERIFY_TOKEN"
AI_MODEL_NAME = "gemini-1.5-flash"
ADMIN_NUMBER = "YOUR_ADMIN_NUMBER"

# ## MODIFIED ##: App setup for SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_me' # Required for sessions
socketio = SocketIO(app, async_mode='eventlet') # ## NEW ##

# Domain and WhatsApp Number for the UI
LIVE_VIEW_DOMAIN = "https://clicky.pyxelworld.com"
WHATSAPP_CONTACT_NUMBER = "+16095314294"
WHATSAPP_NUMBER_CLEANED = ''.join(filter(str.isdigit, WHATSAPP_CONTACT_NUMBER))


# --- PROJECT SETUP ---
BASE_DIR = Path(__file__).parent
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.txt"
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {} # ## MODIFIED ##: Now holds web and WhatsApp sessions
processed_message_ids = set()

# --- (HTML Templates, System Prompt, etc. are defined below) ---

# --- (All helper functions like send_whatsapp_message, etc. are included below) ---

# ## NEW ##: Homepage HTML
HOME_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Magic Clicky - Your AI Web Agent</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        :root {
            --bg-dark: #0d1117; --primary: #0c2d48; --secondary: #145da0; --accent: #2e8bc0;
            --text-light: #e6f1ff; --text-dark: #b1d4e0; --border-color: #30363d;
        }
        body {
            font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-light);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh;
        }
        .container {
            max-width: 800px; text-align: center; padding: 2rem;
            background: rgba(255, 255, 255, 0.05); border-radius: 16px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px); border: 1px solid var(--border-color);
        }
        h1 { font-size: 3rem; color: #fff; margin-bottom: 0.5rem; }
        p.subtitle { font-size: 1.2rem; color: var(--text-dark); margin-bottom: 2.5rem; }
        .tab-container { display: flex; justify-content: center; margin-bottom: 2rem; }
        .tab {
            padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent;
            transition: all 0.3s ease; color: var(--text-dark);
        }
        .tab.active { color: var(--text-light); border-bottom-color: var(--accent); }
        .content { display: none; }
        .content.active { display: block; }
        textarea, input {
            width: 95%; background-color: rgba(0,0,0,0.3); border: 1px solid var(--border-color);
            color: var(--text-light); border-radius: 8px; padding: 12px; font-family: 'Inter', sans-serif;
            font-size: 1rem; margin-bottom: 1rem; resize: vertical;
        }
        button {
            width: 100%; padding: 14px; border: none; border-radius: 8px;
            background-color: var(--secondary); color: #fff; font-size: 1.1rem;
            font-weight: 500; cursor: pointer; transition: background-color 0.3s ease;
        }
        button:hover { background-color: var(--accent); }
        .or-divider { display: flex; align-items: center; text-align: center; color: var(--text-dark); margin: 1.5rem 0; }
        .or-divider::before, .or-divider::after {
            content: ''; flex: 1; border-bottom: 1px solid var(--border-color);
        }
        .or-divider:not(:empty)::before { margin-right: .25em; }
        .or-divider:not(:empty)::after { margin-left: .25em; }
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
    function showTab(tabName) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));
        document.querySelector(`.tab[onclick="showTab('${tabName}')"]`).classList.add('active');
        document.getElementById(tabName).classList.add('active');
    }
    function sendToWhatsApp() {
        const prompt = document.getElementById('whatsapp-prompt').value;
        const encodedPrompt = encodeURIComponent(prompt);
        window.location.href = `https://wa.me/{{ whatsapp_number }}?text=${encodedPrompt}`;
    }
</script>
</body>
</html>
"""

# ## NEW ##: Live View HTML with interactive controls and WebSocket
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
        :root {
            --bg-dark: #0d1117; --primary: #0c2d48; --secondary: #145da0; --accent: #2e8bc0;
            --text-light: #e6f1ff; --text-dark: #b1d4e0; --border-color: #30363d;
            --danger: #b00020; --danger-hover: #d32f2f;
        }
        body {
            font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text-light);
            margin: 0; display: flex; height: 100vh; overflow: hidden;
        }
        .main-content { flex: 3; display: flex; flex-direction: column; padding: 1rem; }
        .sidebar {
            flex: 1; background-color: #010409; border-left: 1px solid var(--border-color);
            display: flex; flex-direction: column; padding: 1rem; height: 100vh;
        }
        .screenshot-container {
            background-color: #010409; border: 1px solid var(--border-color);
            border-radius: 8px; overflow: hidden; flex-grow: 1; display: flex;
            justify-content: center; align-items: center;
        }
        #screenshot { max-width: 100%; max-height: 100%; object-fit: contain; }
        #status-bar {
            background-color: var(--primary); padding: 0.75rem 1rem; border-radius: 8px;
            margin-top: 1rem; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        .sidebar h2 { margin-top: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 0.5rem; }
        .chat-log { flex-grow: 1; overflow-y: auto; margin-bottom: 1rem; }
        .chat-log div {
            padding: 8px; border-radius: 5px; margin-bottom: 8px; max-width: 95%;
            word-wrap: break-word; line-height: 1.4;
        }
        .chat-log .user { background-color: var(--secondary); margin-left: auto; }
        .chat-log .ai { background-color: #21262d; }
        .controls textarea {
            width: 95%; background-color: #21262d; border: 1px solid var(--border-color);
            color: var(--text-light); border-radius: 8px; padding: 10px; font-family: 'Inter', sans-serif;
            font-size: 0.9rem; margin-bottom: 0.5rem; resize: vertical;
        }
        .controls button {
            width: 100%; padding: 10px; border: none; border-radius: 8px;
            background-color: var(--secondary); color: #fff; font-size: 1rem;
            cursor: pointer; transition: background-color 0.3s ease; margin-top: 5px;
        }
        .controls button:hover { background-color: var(--accent); }
        .controls .interrupt-btn { background-color: var(--accent); }
        .controls .interrupt-btn:hover { background-color: var(--secondary); }
        .controls .stop-btn { background-color: var(--danger); }
        .controls .stop-btn:hover { background-color: var(--danger-hover); }
    </style>
</head>
<body>
<div class="main-content">
    <div class="screenshot-container">
        <img id="screenshot" src="" alt="Waiting for session to start...">
    </div>
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

    socket.on('connect', () => {
        console.log('Connected to server!');
        socket.emit('join', { session_id: sessionId });
    });

    socket.on('session_update', (data) => {
        console.log('Received update:', data);
        if (data.image_path) {
            document.getElementById('screenshot').src = data.image_path + '?' + new Date().getTime();
        }
        if (data.status) {
            document.getElementById('status-bar').innerText = "Status: " + data.status;
        }
        if (data.log_message) {
            addLogMessage(data.log_message.sender, data.log_message.text);
        }
    });
    
    socket.on('session_ended', (data) => {
        document.getElementById('status-bar').innerText = "SESSION ENDED: " + data.reason;
        document.querySelectorAll('.controls button, .controls textarea').forEach(el => el.disabled = true);
        addLogMessage('ai', "The session has ended. " + data.reason);
    });

    function addLogMessage(sender, text) {
        const chatLog = document.getElementById('chat-log');
        const msgDiv = document.createElement('div');
        msgDiv.classList.add(sender); // 'user' or 'ai'
        msgDiv.innerText = text;
        chatLog.appendChild(msgDiv);
        chatLog.scrollTop = chatLog.scrollHeight; // Auto-scroll
    }

    function sendMessage() {
        const input = document.getElementById('user-input');
        const message = input.value;
        if (message.trim() === '') return;
        socket.emit('user_command', { session_id: sessionId, command: 'message', value: message });
        addLogMessage('user', message);
        input.value = '';
    }

    function sendControl(commandType) {
        socket.emit('user_command', { session_id: sessionId, command: commandType, value: '' });
        addLogMessage('user', `Sent /${commandType} command.`);
    }

</script>
</body>
</html>
"""

# --- Core Application Logic ---

def send_whatsapp_message(to, text):
    # This function remains the same
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}};
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text message: {e} - {response.text}")

def load_subscribers():
    # This function remains the same
    if not SUBSCRIBERS_FILE.exists(): return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f: return {line.strip() for line in f if line.strip()}
    except IOError as e: print(f"CRITICAL: Could not read subscribers file: {e}"); return set()
subscribers = load_subscribers()

def find_session_by_id(session_id):
    """Finds a session by its UUID across all users."""
    for session in user_sessions.values():
        if session.get('id') == session_id:
            return session
    return None

# ## MODIFIED ##: Centralized session creation for both Web and WhatsApp
def create_new_session(identifier, prompt, session_type="whatsapp"):
    session_id = str(uuid.uuid4())
    user_dir = USER_DATA_DIR / session_id
    user_dir.mkdir(parents=True, exist_ok=True)
    
    session = {
        "id": session_id,
        "identifier": identifier, # WhatsApp number or a web session identifier
        "session_type": session_type, # 'whatsapp' or 'web'
        "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": prompt,
        "user_dir": user_dir, "tab_handles": {}, "is_processing": False, "stop_requested": False,
        "interrupt_requested": False, "cursor_pos": (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2),
        "ocr_results": [], "last_status": "Session initialized. Waiting for prompt.",
        "last_screenshot_path": None, "view_link_sent": False,
        "live_view_updates_on": True # ## NEW ## For /view command
    }
    user_sessions[identifier] = session
    return session

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance..."); options = Options(); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument(f"--window-size={1280},{800}"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try: driver = webdriver.Chrome(options=options); session["driver"] = driver; session["mode"] = "BROWSER"; return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session, reason="Session closed by user."):
    if session.get("driver"):
        print(f"Closing browser for session {session['id']}")
        session["driver"].quit()
        session["driver"] = None
    
    session["mode"] = "CHAT"
    session["is_processing"] = False
    session["stop_requested"] = True
    session["last_status"] = reason

    # Notify the live view that the session has ended
    socketio.emit('session_ended', {'reason': reason}, room=session['id'])
    
    # Clean up the session object from memory after a delay
    identifier = session['identifier']
    if identifier in user_sessions:
        # We don't delete immediately to allow final messages to be sent
        print(f"Session {session['id']} for {identifier} marked for closure.")

# ## MODIFIED ##: This function now emits WebSocket events
def get_page_state(driver, session, status_message):
    screenshot_filename = "live_view.png"
    screenshot_path = session["user_dir"] / screenshot_filename
    session["last_screenshot_path"] = screenshot_path
    session["last_status"] = status_message
    
    try:
        # ... [The complex image generation part is the same] ...
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image, 'RGBA')
        # ... [Drawing grid and cursor] ...
        image.save(screenshot_path)

        # ## NEW ##: Emit the update via WebSocket
        update_data = {
            'status': status_message,
            'image_path': f"/images/{session['id']}/{screenshot_filename}"
        }
        socketio.emit('session_update', update_data, room=session['id'])
        print(f"Emitted session_update for {session['id']}")
        
        # This part is just for the AI's context, not for the user anymore
        window_handles = driver.window_handles
        current_handle = driver.current_window_handle
        tabs = []
        for i, handle in enumerate(window_handles):
            driver.switch_to.window(handle)
            tabs.append(f"Tab {i+1}: {driver.title[:60]}{' (Current)' if handle == current_handle else ''}")
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "\n".join(tabs)
        
        return screenshot_path, tab_info_text

    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, "Error getting page state."

# ## MODIFIED ##: Now takes session object, sends updates to Web and/or WhatsApp
def process_next_browser_step(session, caption):
    from_number = session['identifier'] if session['session_type'] == 'whatsapp' else None
    
    # For web sessions, send a chat log message
    if session['session_type'] == 'web':
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': caption}}, room=session['id'])

    # Send WhatsApp message if it's a WhatsApp session AND live view is off
    if from_number and not session.get('live_view_updates_on', True):
        send_whatsapp_message(from_number, caption)

    screenshot_path, tab_info_text = get_page_state(session["driver"], session, caption)

    if not session.get("view_link_sent"):
        live_view_url = f"{LIVE_VIEW_DOMAIN}/view/{session['id']}"
        if from_number:
            send_whatsapp_message(from_number, f"Estou começando! Acompanhe e controle a sessão em tempo real aqui:\n{live_view_url}")
        session["view_link_sent"] = True

    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\nPrevious Action: {caption}\n{tab_info_text}"
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(session, ai_response)
    else:
        # ... error handling ...

# ## MODIFIED ##: Now takes session object
def process_ai_command(session, ai_response_text):
    if session.get("stop_requested"): return {}
    
    # ... [JSON parsing and error handling are the same] ...
    
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError: # ...
        return {}

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")

    # Send AI's "speak" response to the right channel
    if speak:
        if session['session_type'] == 'whatsapp':
            send_whatsapp_message(session['identifier'], speak)
        socketio.emit('session_update', {'log_message': {'sender': 'ai', 'text': speak}}, room=session['id'])

    # ... [The big `if/elif` block for commands is mostly the same] ...
    # Main change is calling process_next_browser_step(session, caption)
    # And for END_BROWSER, call close_browser(session, reason)

    try:
        if command == "END_BROWSER":
            reason = params.get('reason', 'N/A')
            close_browser(session, f"Task Completed. Summary: {reason}")
            if session['session_type'] == 'whatsapp':
                send_whatsapp_message(session['identifier'], f"*Tarefa Concluída.*\n*Resumo:* {reason}")
            return command_data
        
        # ... all other commands ...

        # At the end of the try block:
        if action_in_browser: time.sleep(2)
        socketio.start_background_task(process_next_browser_step, session, next_step_caption)

    except Exception as e:
        # ... error handling ...
        socketio.start_background_task(process_next_browser_step, session, error_summary)

# --- Flask Routes and WebSocket Events ---

@app.route('/')
def home():
    return render_template_string(HOME_PAGE_TEMPLATE, whatsapp_number=WHATSAPP_NUMBER_CLEANED)

@app.route('/start-web-session', methods=['POST'])
def start_web_session():
    prompt = request.form.get('prompt')
    if not prompt: return "Prompt is required.", 400
    
    # Use the session ID itself as the identifier for web sessions
    session_id = str(uuid.uuid4())
    session = create_new_session(identifier=session_id, prompt=prompt, session_type="web")
    session['is_processing'] = True
    
    # Kick off the AI process in the background
    socketio.start_background_task(target=run_initial_ai, session=session, user_message=prompt)
    
    return redirect(url_for('view_session', session_id=session.get('id')))

def run_initial_ai(session, user_message):
    """Function to run the first AI call in a background thread."""
    session["chat_history"].append({"role": "user", "parts": [user_message]})
    ai_response = call_ai(session["chat_history"], context_text=f"New task: {user_message}")
    process_ai_command(session, ai_response)

@app.route('/view/<session_id>')
def view_session(session_id):
    session = find_session_by_id(session_id)
    if not session:
        return "Session not found or has expired.", 404
    return render_template_string(LIVE_VIEW_TEMPLATE, session_id=session_id)

# ... [image and data routes are the same as before] ...

@socketio.on('join')
def on_join(data):
    session_id = data['session_id']
    from flask import request as flask_request
    join_room(session_id, sid=flask_request.sid)
    print(f"Client joined room: {session_id}")
    # You could optionally send the latest state immediately upon join

@socketio.on('user_command')
def handle_user_command(data):
    session_id = data.get('session_id')
    command = data.get('command')
    value = data.get('value')
    session = find_session_by_id(session_id)
    if not session: return

    if command == 'message':
        if session.get("is_processing"):
            socketio.emit('session_update', {'log_message': {'sender':'ai', 'text':"Working... please Interrupt first to send a new message."}}, room=session_id)
            return
        session['is_processing'] = True
        session["chat_history"].append({"role": "user", "parts": [value]})
        socketio.start_background_task(process_next_browser_step, session, f"User Guidance: {value}")
    
    elif command == 'interrupt':
        session['interrupt_requested'] = True
        session['is_processing'] = False
        socketio.emit('session_update', {'status': 'Interrupted. Ready for new command.'}, room=session_id)

    elif command == 'stop':
        close_browser(session, reason="Session stopped by user via web interface.")


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # ... [GET request logic is the same] ...
    if request.method == 'POST':
        # ... [message parsing and subscriber check logic is the same] ...
        
        user_message_text = message_info["text"]["body"]
        from_number = message_info["from"]
        command_text = user_message_text.strip().lower()

        # ## NEW ##: Handle /view command
        if command_text == '/view':
            session = user_sessions.get(from_number)
            if session:
                session['live_view_updates_on'] = not session.get('live_view_updates_on', True)
                status = "ATIVADO" if session['live_view_updates_on'] else "DESATIVADO"
                send_whatsapp_message(from_number, f"Modo de visualização ao vivo {status}. Quando ativado, as atualizações de passo a passo não serão enviadas aqui.")
            else:
                send_whatsapp_message(from_number, "Nenhuma sessão ativa para configurar. Inicie uma tarefa primeiro.")
            return Response(status=200)

        # ... [/stop, /interrupt, /clear logic is the same] ...

        # When starting a new session from WhatsApp:
        session = create_new_session(identifier=from_number, prompt=user_message_text, session_type="whatsapp")
        session['is_processing'] = True
        socketio.start_background_task(target=run_initial_ai, session=session, user_message=user_message_text)

    return Response(status=200)


# (The rest of the functions like find_text_in_ocr, call_ai, etc. are needed but unchanged)
# I will omit them here for brevity, but they should be in your final file.

if __name__ == '__main__':
    print("--- Magic Clicky Server with Web UI & Live Control ---")
    # Use socketio.run() to start the server
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
