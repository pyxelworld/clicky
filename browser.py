import os
import json
import requests
import time
import io
import traceback
from urllib.parse import quote_plus
from flask import Flask, request, Response
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import mss # <-- NEW: Import the OS-level screenshot library
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# --- CONFIGURATION ---
# Rotating API keys
GEMINI_API_KEYS = [
    "AIzaSyCnnkNB4qPXE9bgTwRH_Jj5lxUOq_xivJo",
    "AIzaSyDuAT3AP1wNd-FNb0QmvwQcSTD2dM3ZStc",
    "AIzaSyCuKxOa7GoY6id_aG-C3_uhvfJ1iI0SeQ0",
    "AIzaSyBwASUXeAVJ6xFFZdfjNZO5Hsumr4KAntw",
    "AIzaSyB4EZanzOFSu589lfBVO3M8dy72fBW2ObY",
    "AIzaSyASbyRix7Cbae7qCgPQntshA5DVJSVJbo4",
    "AIzaSyD07UM2S3qdSUyyY0Hp4YtN04J60PcO41w",
    "AIzaSyA9037TcPXJ2tdSrEe-hzLCn0Xa5zjiUOo",
]
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
AI_MODEL_NAME = "gemini-2.0-flash"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- CONSTANTS ---
CUSTOM_SEARCH_URL_BASE = "https://www.bing.com"
CUSTOM_SEARCH_URL_TEMPLATE = "https://www.bing.com/search?q=%s"
GRID_CELL_SIZE = 40

# --- JAVASCRIPT IS NO LONGER NEEDED FOR LABELS ---

# --- MODIFIED: SYSTEM PROMPT FOR GRID-ONLY OPERATION ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You operate by receiving a state (a screenshot and tab info) and issuing a single command in JSON format.

--- NEW OPERATING-MODE: GRID ONLY ---
Your view is now a screenshot of the ENTIRE browser, including the address bar and tabs. This view is overlaid with a coordinate grid (A1, B2, C3, etc.).
ALL interactions with the page, including clicking links, buttons, and input fields, MUST be done using the `GRID_CLICK` command. There is no other way to click.

--- ERROR RECOVERY ---
If a command fails, the page may have changed unexpectedly or the command was invalid. Analyze the new screenshot and the error message provided. Do not repeat the failed command. Instead, assess the situation and issue a new command to recover or proceed.

--- GUIDING PRINCIPLES ---

1.  **CLICKING STRATEGY:** Identify the element you want to interact with on the grid and issue a `GRID_CLICK` command with the correct cell (e.g., 'C5', 'G12'). This applies to everything: links, buttons, browser controls, etc.

2.  **TYPING STRATEGY:** To type into a text box, you MUST FIRST issue a `GRID_CLICK` command on the text box itself. On the next turn, after the click is confirmed, you can issue the `TYPE` command.

3.  **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down on a page after it loads or after an action. The initial view is only the top of the page. You must scroll to understand the full context. Use `GRID_CLICK` on the scrollbar if visible, or use the `SCROLL` command.

4.  **SEARCH STRATEGY:** To search the web, you MUST use the `CUSTOM_SEARCH` command with "Bing".

5.  **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt to fill it in. Stop and ask the user for permission using the `PAUSE_AND_ASK` command.

6.  **HANDLING OBSTACLES (CAPTCHA):** If you land on a page with a standard CAPTCHA, use `GRID_CLICK` on the checkbox. If it's a more complex "select all images" CAPTCHA, you cannot solve it. Use the `GO_BACK` command.

--- YOUR RESPONSE FORMAT ---

Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE (GRID-ONLY) ---

**== BROWSER START/STOP COMMANDS ==**
1.  **`START_BROWSER`**: Initiates a new browser session.
2.  **`END_BROWSER`**: Closes the browser.

**== NAVIGATION COMMANDS ==**
3.  **`NAVIGATE`**: Goes directly to a URL.
4.  **`CUSTOM_SEARCH`**: Performs a search using "Bing".
5.  **`GO_BACK`**: Navigates to the previous page in history.

**== PAGE INTERACTION COMMANDS ==**
6.  **`GRID_CLICK`**: (PRIMARY ACTION) Clicks the center of a specified grid cell.
    - **Params:** `{"cell": "<e.g., 'C5', 'G12'>"}`
    - **Example:** `{"command": "GRID_CLICK", "params": {"cell": "D10"}, "thought": "The 'Login' button is in cell D10. I will now click it.", "speak": "Clicking D10."}`

7.  **`TYPE`**: Types text. You MUST `GRID_CLICK` an input field first.
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`

8.  **`SCROLL`**: Scrolls the page up or down.
    - **Params:** `{"direction": "<up|down>"}`

**== TAB MANAGEMENT COMMANDS ==**
9.  **`NEW_TAB`**, **`SWITCH_TO_TAB`**, **`CLOSE_TAB`**

**== USER INTERACTION COMMANDS ==**
10. **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
11. **`SPEAK`**: For simple conversation.
"""

def send_whatsapp_message(to, text):
    """Sends a simple text message."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp text message: {e} - {response.text}")

def send_whatsapp_image(to, image_path, caption=""):
    """Uploads an image and sends it to the user."""
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': (image_path.name, open(image_path, 'rb'), 'image/png'), 'messaging_product': (None, 'whatsapp'), 'type': (None, 'image/png')}
    media_id = None
    try:
        response = requests.post(upload_url, headers=headers, files=files)
        response.raise_for_status()
        media_id = response.json().get('id')
    except requests.exceptions.RequestException as e:
        print(f"Error uploading WhatsApp media: {e} - {response.text}")
        return
    if not media_id:
        print("Failed to get media ID from WhatsApp upload.")
        return
    send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
    try:
        requests.post(send_url, headers=headers, json=data).raise_for_status()
        print(f"Sent image message to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp image message: {e} - {response.text}")

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "tab_handles": {},
            "is_processing": False,
            "stop_requested": False, "interrupt_requested": False
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver; session["mode"] = "BROWSER"
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        print("Reminder: If on a server, you must use 'xvfb-run' to launch this script.")
        traceback.print_exc()
        return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["tab_handles"] = {}

# --- REWRITTEN: get_page_state using mss for full screen capture ---
def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    
    # Get Tab Info (this part remains the same)
    tab_info_text = ""
    try:
        window_handles = driver.window_handles; current_handle = driver.current_window_handle; tabs = []
        session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1; session["tab_handles"][tab_id] = handle; driver.switch_to.window(handle)
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e:
        print(f"Could not get tab info: {e}")
    
    # Full Screen Capture with Grid
    try:
        with mss.mss() as sct:
            # Get a screenshot of the primary monitor
            sct_img = sct.grab(sct.monitors[1])
            # Create an Image
            image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=12)
        except IOError:
            font = ImageFont.load_default()

        # Draw grid over the entire image
        cols = image.width // GRID_CELL_SIZE
        rows = image.height // GRID_CELL_SIZE
        for i in range(rows):
            for j in range(cols):
                x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")
                label = f"{chr(ord('A')+j)}{i+1}"
                draw.text((x1 + 2, y1 + 2), label, fill="red", font=font)
        
        image.save(screenshot_path)
        print("State captured with full UI in GRID mode.")
        # Labels text is now just a note about grid mode
        labels_text = "GRID MODE ONLY: The view shows the entire browser. Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
        return screenshot_path, labels_text, tab_info_text
        
    except Exception as e:
        print(f"Error getting page state with mss: {e}")
        traceback.print_exc()
        return None, "", tab_info_text


def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: {e}"}, "thought": "Image read failed.", "speak": "Error with screen view."})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt_parts)
            print("AI call successful."); return response.text
        except Exception as e: print(f"API key #{i+1} failed. Error: {e}"); last_error = e; continue
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Error connecting to my brain."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, labels_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{labels_text}\n\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "Could not get a view of the page. I will close the browser."); close_browser(session)

# --- MODIFIED: process_ai_command for GRID-ONLY ---
def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    
    if session.get("stop_requested"):
        print("Stop was requested, ignoring AI command.")
        session["stop_requested"] = False
        session["chat_history"] = []
        return
    if session.get("interrupt_requested"):
        print("Interrupt was requested, ignoring AI command.")
        session["interrupt_requested"] = False
        return

    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        if session["mode"] == "BROWSER": close_browser(session)
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    driver = session.get("driver")
    
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER"]:
        send_whatsapp_message(from_number, "The browser was closed. I'm starting it up to continue your task...")
        driver = start_browser(session)
        if not driver:
            send_whatsapp_message(from_number, "I failed to restart the browser. Please start a new task.")
            close_browser(session); return
        time.sleep(1)
        process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        # Removed SWITCH_TO_GRID/LABEL commands as it's always grid
        if command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                send_whatsapp_message(from_number, f"Invalid cell format: {cell}.")
                action_was_performed = False
            else:
                # Use ActionChains to click on the screen coordinates, not a web element
                col_index = ord(cell[0]) - ord('A')
                row_index = int(cell[1:]) - 1
                x = col_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                y = row_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                print(f"Grid clicking at SCREEN coordinates ({x}, {y}) for cell {cell}")
                
                ActionChains(driver).move_by_offset(int(x), int(y)).click().perform()
                # Reset offset for the next action
                ActionChains(driver).move_by_offset(int(-x), int(-y)).perform()

        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
            process_next_browser_step(from_number, session, "Browser started. What's next?")
            return
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH":
            driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "NEW_TAB": driver.switch_to.new_window('tab'); driver.get(params["url"]) if "url" in params and params["url"] else None
        elif command == "CLOSE_TAB":
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
            else: send_whatsapp_message(from_number, "I can't close the last tab."); action_was_performed = False
        elif command == "SWITCH_TO_TAB":
            handle = session["tab_handles"].get(params.get("tab_id"))
            if handle: driver.switch_to.window(handle)
            else: send_whatsapp_message(from_number, "I couldn't find that tab ID."); action_was_performed = False
        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {800 if params.get('direction', 'down') == 'down' else -800});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command == "PAUSE_AND_ASK": return
        elif command == "SPEAK": return
        else: print(f"Unknown command: {command}"); send_whatsapp_message(from_number, f"Unknown command '{command}'."); action_was_performed = True
        
        if action_was_performed: time.sleep(2); process_next_browser_step(from_number, session, f"Action done: {speak}")
    except Exception as e:
        error_summary = f"Error during command '{command}': {e}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, f"An action failed. I will show the AI what happened so it can try to recover.")
        time.sleep(1)
        process_next_browser_step(from_number, session, caption=f"An error occurred: {error_summary}. What should I do now?")

# The webhook remains the same
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

            if message_id in processed_message_ids:
                print(f"Duplicate message ID {message_id} received. Ignoring."); return Response(status=200)
            processed_message_ids.add(message_id)
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I only process text messages."); return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            command_text = user_message_text.strip().lower()
            if command_text == "/stop":
                print(f"User {from_number} issued /stop command.")
                session["stop_requested"] = True
                close_browser(session)
                session["is_processing"] = False
                send_whatsapp_message(from_number, "Request stopped. Your current task has been cancelled. Any pending actions will be ignored.")
                return Response(status=200)

            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                if session["mode"] != "BROWSER":
                    send_whatsapp_message(from_number, "There is no browser task to interrupt.")
                else:
                    session["interrupt_requested"] = True
                    session["is_processing"] = False
                    send_whatsapp_message(from_number, "Interrupted. The current action will be ignored. What would you like to do instead?")
                return Response(status=200)

            if command_text == "/clear":
                print(f"User {from_number} issued /clear command.")
                close_browser(session)
                if from_number in user_sessions:
                    del user_sessions[from_number]
                send_whatsapp_message(from_number, "Your session and chat history have been cleared.")
                print(f"Session for {from_number} cleared.")
                return Response(status=200)

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "Please wait, I'm still working on your previous request. You can use /interrupt to stop the current action or /stop to end the task completely."); return Response(status=200)
            
            try:
                session["is_processing"] = True
                session["chat_history"].append({"role": "user", "parts": [user_message_text]})

                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=user_message_text)
                    process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    process_next_browser_step(from_number, session, f"Continuing with new instructions from user: {user_message_text}")
            finally:
                if not session.get("interrupt_requested"):
                    session["is_processing"] = False

        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
