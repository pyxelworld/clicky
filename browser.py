import os
import json
import requests
import time
import io
import traceback
import subprocess
from urllib.parse import quote_plus
from flask import Flask, request, Response
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# --- NEW DESKTOP AUTOMATION LIBRARIES ---
import pyautogui

# --- CONFIGURATION ---
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
BING_SEARCH_URL_TEMPLATE = "https://www.bing.com/search?q=%s"
# MODIFIED: Larger grid cells for a cleaner look
GRID_CELL_SIZE = 80

# --- COMPLETELY REWRITTEN SYSTEM PROMPT FOR DESKTOP AUTOMATION ---
SYSTEM_PROMPT = """
You are "Magic Agent," an AI expert controlling a complete computer desktop. You operate by receiving a full-screen screenshot and issuing commands to move the mouse and use the keyboard, just like a human.

--- YOUR WORLDVIEW ---
1.  **You see the ENTIRE screen.** This includes the web browser's UI (tabs, address bar), the operating system's taskbar, and any open windows.
2.  **You ONLY operate in GRID MODE.** The screen is overlaid with a coordinate grid (A1, B2, C3, etc.). All of your actions MUST be based on this grid. There is no "Label Mode".
3.  **Think step-by-step.** Complex actions require multiple simple commands. For example, opening a new website is not one command, but three: CLICK the address bar, TYPE the URL, PRESS the 'enter' key.

--- GUIDING PRINCIPLES ---
1.  **NAVIGATION:** To go to a website, you must first `GRID_CLICK` the browser's address bar. Then, use the `TYPE` command to enter the URL. Finally, use the `PRESS_KEY` command with "enter".
2.  **SEARCHING:** To search, you must first `GRID_CLICK` the browser's address bar, then `TYPE` your search query, and then `PRESS_KEY` with "enter". The browser is set to search with Bing by default.
3.  **TYPING IN FIELDS:** Before you can type in a text box on a webpage, you MUST `GRID_CLICK` it first to select it.
4.  **SCROLLING:** If you need to see more of a page, use the `SCROLL` command.
5.  **RECOVERY:** If an action doesn't work as expected (e.g., a click did nothing), analyze the new screenshot. Is there a popup? Did the page change? Formulate a new plan. Do not repeat the exact same failed command.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

1.  **`GRID_CLICK`**: (PRIMARY ACTION) Clicks the center of a specified grid cell. This is used for everything: clicking buttons, links, address bars, tabs, etc.
    - **Params:** `{"cell": "<e.g., 'C5', 'G12'>"}`
    - **Example:** `{"command": "GRID_CLICK", "params": {"cell": "F2"}, "thought": "I need to click the address bar to type a new URL. It is in cell F2.", "speak": "Clicking the address bar."}`

2.  **`TYPE`**: Types text at the current cursor position. You MUST `GRID_CLICK` a text field or address bar first.
    - **Params:** `{"text": "<text_to_type>"}`
    - **Example:** `{"command": "TYPE", "params": {"text": "weather in New York"}, "thought": "Now that the address bar is selected, I will type my search query.", "speak": "Searching for the weather in New York."}`

3.  **`PRESS_KEY`**: Presses a special keyboard key once. Essential for submitting forms and navigating.
    - **Params:** `{"key": "<key_name>"}`
    - **Supported Keys:** `enter`, `up`, `down`, `left`, `right`, `tab`, `esc` (escape), `backspace`, `delete`, `pageup`, `pagedown`. For key combinations like Ctrl+A, use the `HOTKEY` command.
    - **Example:** `{"command": "PRESS_KEY", "params": {"key": "enter"}, "thought": "I have typed the URL, now I will press enter to navigate.", "speak": "Going to the website."}`

4.  **`HOTKEY`**: Presses a combination of keys.
    - **Params:** `{"keys": ["<key1>", "<key2>"]}` (e.g., ["ctrl", "a"])
    - **Example:** `{"command": "HOTKEY", "params": {"keys": ["ctrl", "a"]}, "thought": "I will select all text in the address bar before typing over it.", "speak": "Clearing the address bar."}`

5.  **`SCROLL`**: Scrolls the mouse wheel up or down from the current mouse position.
    - **Params:** `{"direction": "<up|down>"}`

6.  **`START_BROWSER`**: Opens a new Chrome browser window.
    - **Params:** `{}`

7.  **`END_BROWSER`**: Closes the browser and ends the task.
    - **Params:** `{"reason": "<summary>"}`

8.  **`PAUSE_AND_ASK`**: Pauses to ask the user a clarifying question.
    - **Params:** `{"question": "<your_question>"}`

9.  **`SPEAK`**: For simple conversation or stating the task is complete without ending the browser.
    - **Params:** `{"text": "<your_response>"}`
"""

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

def send_whatsapp_image(to, image_path, caption=""):
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
            "mode": "CHAT", "browser_process": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "is_processing": False,
            "stop_requested": False, "interrupt_requested": False
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("browser_process") and session["browser_process"].poll() is None:
        print("Browser process is already running.")
        return session["browser_process"]
    print("Starting new browser instance via subprocess...")
    # MODIFIED: Launch chrome as a separate process
    # Note: Assumes 'google-chrome' is in the system's PATH.
    # The --user-data-dir is kept for session persistence (cookies, etc.)
    user_profile_path = session['user_dir'] / 'chrome_profile'
    command = [
        "google-chrome",
        "--window-size=1280,800",
        f"--user-data-dir={user_profile_path}"
    ]
    try:
        process = subprocess.Popen(command)
        session["browser_process"] = process
        session["mode"] = "BROWSER"
        # Give the browser time to open
        time.sleep(3)
        return process
    except FileNotFoundError:
        print("CRITICAL: 'google-chrome' command not found. Please ensure it is installed and in your PATH.")
        return None
    except Exception as e:
        print(f"CRITICAL: Error starting browser process: {e}")
        traceback.print_exc()
        return None

def close_browser(session):
    if session.get("browser_process"):
        print(f"Closing browser process for session {session['user_dir'].name}")
        try:
            session["browser_process"].terminate()
            session["browser_process"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            session["browser_process"].kill()
        except Exception as e:
            print(f"Error closing browser process: {e}")
        session["browser_process"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""

def get_page_state(session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    try:
        # MODIFIED: Take a screenshot of the entire desktop
        image = pyautogui.screenshot()
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=16)
        except IOError:
            font = ImageFont.load_default()

        # MODIFIED: Grid is now the only mode and covers the whole screen
        cols = image.width // GRID_CELL_SIZE
        rows = image.height // GRID_CELL_SIZE
        for i in range(rows):
            for j in range(cols):
                x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")
                label = f"{chr(ord('A')+j)}{i+1}"
                # Draw text with a small black outline for better visibility
                draw.text((x1 + 3, y1 + 3), label, fill="black", font=font)
                draw.text((x1 + 2, y1 + 2), label, fill="red", font=font)
        
        image.save(screenshot_path)
        print("Full desktop state captured.")
        # We no longer have browser-specific info like tabs or labels
        return screenshot_path, "GRID MODE: Full desktop view.", ""
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, "", ""

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
    screenshot_path, labels_text, _ = get_page_state(session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{labels_text}\n\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "Could not get a view of the screen. I will close the browser."); close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    
    if session.get("stop_requested"):
        print("Stop was requested..."); session["stop_requested"] = False; session["chat_history"] = []; return
    if session.get("interrupt_requested"):
        print("Interrupt was requested..."); session["interrupt_requested"] = False; return

    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        if session["mode"] == "BROWSER": close_browser(session)
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    # Check if browser is running before executing browser commands
    if session.get("mode") == "BROWSER" and (not session.get("browser_process") or session.get("browser_process").poll() is not None):
        if command not in ["START_BROWSER", "SPEAK"]:
             send_whatsapp_message(from_number, "The browser was closed unexpectedly. I will try to restart it.")
             start_browser(session)
             time.sleep(2)

    try:
        action_was_performed = True
        if command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                send_whatsapp_message(from_number, f"Invalid cell format: {cell}."); action_was_performed = False
            else:
                col_index = ord(cell[0]) - ord('A')
                row_index = int(cell[1:]) - 1
                x = col_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                y = row_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                print(f"Clicking screen at ({x}, {y}) for cell {cell}")
                pyautogui.click(x, y)
        elif command == "TYPE":
             text_to_type = params.get("text", "")
             print(f"Typing text: {text_to_type}")
             pyautogui.write(text_to_type, interval=0.05)
        elif command == "PRESS_KEY":
            key = params.get("key", "").lower()
            if key in ['enter', 'up', 'down', 'left', 'right', 'tab', 'esc', 'backspace', 'delete', 'pageup', 'pagedown']:
                print(f"Pressing key: {key}")
                pyautogui.press(key)
            else:
                action_was_performed = False
                send_whatsapp_message(from_number, f"Unsupported key: {key}")
        elif command == "HOTKEY":
            keys = params.get("keys", [])
            if len(keys) > 1:
                print(f"Pressing hotkey: {keys}")
                pyautogui.hotkey(*keys)
            else:
                 action_was_performed = False
                 send_whatsapp_message(from_number, "Hotkey requires at least two keys.")
        elif command == "SCROLL":
            direction = -100 if params.get('direction', 'down') == 'down' else 100
            print(f"Scrolling {'down' if direction < 0 else 'up'}")
            pyautogui.scroll(direction)
        elif command == "START_BROWSER":
            if not start_browser(session):
                send_whatsapp_message(from_number, "Could not open browser."); return
        elif command == "END_BROWSER":
            send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}");
            close_browser(session); return
        elif command in ["PAUSE_AND_ASK", "SPEAK"]:
            return
        else:
            print(f"Unknown command: {command}");
            send_whatsapp_message(from_number, f"Unknown command '{command}'.");
            action_was_performed = True
        
        if action_was_performed:
            time.sleep(2)
            process_next_browser_step(from_number, session, f"Action done: {speak}")

    except Exception as e:
        error_summary = f"Error during command '{command}': {e}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, f"A desktop action failed. I will show the AI what happened so it can try to recover.")
        time.sleep(1)
        process_next_browser_step(from_number, session, caption=f"An error occurred: {error_summary}. What should I do now?")


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
                send_whatsapp_message(from_number, "Request stopped. Your current task has been cancelled.")
                return Response(status=200)

            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                session["interrupt_requested"] = True
                session["is_processing"] = False
                send_whatsapp_message(from_number, "Interrupted. What would you like to do instead?")
                return Response(status=200)

            if command_text == "/clear":
                print(f"User {from_number} issued /clear command.")
                close_browser(session)
                if from_number in user_sessions:
                    del user_sessions[from_number]
                send_whatsapp_message(from_number, "Your session and chat history have been cleared.")
                return Response(status=200)

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "Please wait, I'm working. Use /interrupt to stop the current action or /stop to end the task."); return Response(status=200)
            
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
    print("--- Magic Agent Desktop Automation Server ---")
    app.name = 'whatsapp'
    # IMPORTANT: Ensure this is run with xvfb-run on a headless server
    app.run(port=5000, debug=False)
