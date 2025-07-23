import os
import json
import requests
import time
import io
import traceback
from urllib.parse import quote_plus
from flask import Flask, request, Response
from pathlib import Path
import subprocess # To start Chrome
import pyautogui # To control mouse/keyboard
import mss # To take fast screenshots
import pytesseract # To read text from images
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

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
# MODIFIED: Grid is now much larger for full-screen control
GRID_WIDTH = 20
GRID_HEIGHT = 20

# --- NEW SYSTEM PROMPT FOR DESKTOP AUTOMATION ---
SYSTEM_PROMPT = """
You are "Magic Agent," an AI expert at controlling a computer's desktop. You see the entire screen and can click anywhere or type. You operate by receiving a screenshot and issuing a single command in JSON format.

--- GUIDING PRINCIPLES ---
1.  **FULL SCREEN AWARENESS:** The screenshot you receive is the ENTIRE desktop. You can see and interact with the browser's UI (tabs, address bar) and any other application.
2.  **GRID IS PREFERRED:** Your primary method of clicking should be `GRID_CLICK`. The grid covers the whole screen. Use it to click on tabs, buttons, links, or any other UI element.
3.  **TEXT-BASED CLICKS:** If you cannot easily use the grid, or for very clear targets, use the `CLICK_TEXT` command. Specify the exact text you see on the screen that you want to click on. For example, `CLICK_TEXT "Sign In"`.
4.  **TYPING:** To type, you must first click on an input field using `GRID_CLICK` or `CLICK_TEXT`, then use the `TYPE` command.
5.  **SEARCHING:** To search, you must first click the browser's address bar (using the grid), then `TYPE` your search query, and finally `PRESS_KEY` to hit 'enter'.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

1.  **`GRID_CLICK`**: (PRIMARY) Clicks the center of a specified grid cell on the screen.
    - **Params:** `{"cell": "<e.g., 'C5', 'G12'>"}`
    - **Example:** `{"command": "GRID_CLICK", "params": {"cell": "D2"}, "thought": "The address bar is in cell D2. I will click it to start typing.", "speak": "Clicking the address bar."}`

2.  **`CLICK_TEXT`**: Clicks on the first place the specified text is found on the screen.
    - **Params:** `{"text": "<text_to_find>"}`
    - **Example:** `{"command": "CLICK_TEXT", "params": {"text": "Images"}, "thought": "I will click on the 'Images' link to switch to image search results.", "speak": "Clicking on 'Images'."}`

3.  **`TYPE`**: Types text at the current cursor location. You MUST click an input field first.
    - **Params:** `{"text": "<text_to_type>"}`

4.  **`PRESS_KEY`**: Presses a special key.
    - **Params:** `{"key": "<enter|esc|up|down|left|right>"}`

5.  **`SCROLL`**: Scrolls the mouse wheel.
    - **Params:** `{"direction": "<up|down>"}`

6.  **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
    - **Params:** `{"question": "<your_question>"}`
    
7.  **`FINISH`**: Ends the task when it is fully complete.
    - **Params:** `{"reason": "<summary>"}`
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
    try:
        response = requests.post(upload_url, headers=headers, files=files)
        response.raise_for_status()
        media_id = response.json().get('id')
        if not media_id:
            print("Failed to get media ID from WhatsApp upload.")
            return
        send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
        requests.post(send_url, headers=headers, json=data).raise_for_status()
        print(f"Sent image message to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending/uploading WhatsApp image message: {e} - {getattr(e, 'response', '') and e.response.text}")


def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "browser_process": None, "chat_history": [], "original_prompt": ""
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("browser_process"): return
    print("Starting new browser instance...")
    try:
        # Just open Chrome, don't control it. PyAutoGUI will do the rest.
        session["browser_process"] = subprocess.Popen(["google-chrome", "--start-maximized", "--no-first-run"])
        time.sleep(2) # Give it a moment to open
    except Exception as e:
        print(f"CRITICAL: Error starting Chrome: {e}")
        print("Reminder: If on a server, you must use 'xvfb-run' to launch this script.")
        traceback.print_exc()

def close_browser(session):
    if session.get("browser_process"):
        print(f"Closing browser for session...")
        try:
            session["browser_process"].terminate()
            session["browser_process"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            session["browser_process"].kill()
        except Exception as e:
            print(f"Error closing browser: {e}")
        session["browser_process"] = None

def get_screen_state(session):
    screenshot_path = USER_DATA_DIR / f"state_{int(time.time())}.png"
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] # sct.monitors[0] is the whole desktop, [1] is the primary monitor
            img = sct.grab(monitor)
            image = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        
        draw = ImageDraw.Draw(image)
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=16)
        except IOError: font = ImageFont.load_default(size=16)

        screen_width, screen_height = image.size
        cell_width = screen_width / GRID_WIDTH
        cell_height = screen_height / GRID_HEIGHT

        for i in range(GRID_HEIGHT):
            for j in range(GRID_WIDTH):
                x1, y1 = j * cell_width, i * cell_height
                draw.rectangle([x1, y1, x1 + cell_width, y1 + cell_height], outline="rgba(255,0,0,100)")
                label = f"{chr(ord('A')+j)}{i+1}"
                draw.text((x1 + 3, y1 + 3), label, fill="red", font=font)
        
        image.save(screenshot_path)
        return screenshot_path
    except Exception as e:
        print(f"Error getting screen state: {e}")
        traceback.print_exc()
        return None

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e: return json.dumps({"command": "FINISH", "params": {"reason": f"Error reading screen: {e}"}, "thought": "Image read failed.", "speak": "I'm having trouble seeing the screen."})
    
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
            if i == len(GEMINI_API_KEYS) - 1:
                return json.dumps({"command": "FINISH", "params": {"reason": f"AI API error: {e}"}, "thought": "All API keys failed.", "speak": "I'm having trouble connecting to my brain."})

def process_next_step(from_number, session, caption=""):
    screenshot_path = get_screen_state(session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "I couldn't get a view of the screen. Ending the task.")
        close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    try:
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, "I received an invalid response from my brain. Let me try again.")
        print(f"Invalid JSON from AI: {ai_response_text}")
        process_next_step(from_number, session, "The last command was invalid. Please try again.")
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    try:
        if command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                raise ValueError(f"Invalid cell format: {cell}")
            
            screen_width, screen_height = pyautogui.size()
            cell_width = screen_width / GRID_WIDTH
            cell_height = screen_height / GRID_HEIGHT
            col_index = ord(cell[0]) - ord('A')
            row_index = int(cell[1:]) - 1
            x = col_index * cell_width + (cell_width / 2)
            y = row_index * cell_height + (cell_height / 2)
            
            print(f"Clicking cell {cell} at coordinates ({int(x)}, {int(y)})")
            pyautogui.click(x, y)

        elif command == "CLICK_TEXT":
            text_to_find = params.get("text")
            if not text_to_find: raise ValueError("No text provided for CLICK_TEXT")
            
            # Use OCR to find the text on the screen
            screenshot = pyautogui.screenshot()
            ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            
            found = False
            for i, text in enumerate(ocr_data['text']):
                if text_to_find.lower() in text.lower():
                    x = ocr_data['left'][i] + ocr_data['width'][i] / 2
                    y = ocr_data['top'][i] + ocr_data['height'][i] / 2
                    print(f"Found text '{text_to_find}' at ({int(x)}, {int(y)}). Clicking.")
                    pyautogui.click(x, y)
                    found = True
                    break
            if not found:
                raise ValueError(f"Could not find text '{text_to_find}' on the screen.")

        elif command == "TYPE":
            pyautogui.typewrite(params.get("text", ""), interval=0.05)

        elif command == "PRESS_KEY":
            pyautogui.press(params.get("key", "enter"))
            
        elif command == "SCROLL":
            scroll_amount = -500 if params.get('direction', 'down') == 'down' else 500
            pyautogui.scroll(scroll_amount)

        elif command == "FINISH":
            send_whatsapp_message(from_number, f"*Task Finished:*\n{params.get('reason', 'Done.')}")
            close_browser(session)
            return

        elif command == "PAUSE_AND_ASK":
             # This command now just waits for the user's next message
            return

        else:
            raise ValueError(f"Unknown command: {command}")
        
        time.sleep(2) # Wait for the UI to react
        process_next_step(from_number, session, f"Action done: {speak}")

    except Exception as e:
        error_summary = f"Error during command '{command}': {e}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, f"An action failed. I will show the AI what happened so it can try to recover.")
        time.sleep(1)
        process_next_step(from_number, session, caption=f"An error occurred: {error_summary}. What should I do now?")


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
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I only process text messages."); return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)

            session["chat_history"].append({"role": "user", "parts": [user_message_text]})

            if not session.get("browser_process"): # First message of a task
                session["original_prompt"] = user_message_text
                start_browser(session)
                # Now that the browser is open, immediately process the first step
                process_next_step(from_number, session, "Browser started. Here is the screen. What should I do first?")
            else: # Follow-up message during a task
                process_next_step(from_number, session, f"Continuing with new instructions from user: {user_message_text}")

        except Exception as e:
            print(f"Error in webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent Desktop Automator ---")
    pyautogui.FAILSAFE = False # Disables the failsafe that moves mouse to corner to stop
    app.run(port=5000, debug=False)
