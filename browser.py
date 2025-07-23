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
AI_MODEL_NAME = "gemini-1.5-flash"

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
GRID_CELL_SIZE = 100

# --- JAVASCRIPT SNIPPETS ---
JS_FIND_TEXT_LOCATIONS = """
    const textToFind = arguments[0];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    const locations = [];
    let node;
    while (node = walker.nextNode()) {
        if (node.nodeValue.trim().includes(textToFind)) {
            const range = document.createRange();
            range.selectNode(node);
            const rect = range.getBoundingClientRect();
            if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)) {
                locations.push({
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height
                });
            }
        }
    }
    // De-duplicate overlapping boxes
    const uniqueLocations = [];
    locations.forEach(loc => {
        let isOverlapping = uniqueLocations.some(uniqueLoc => {
            return !(loc.x > uniqueLoc.x + uniqueLoc.width || 
                     loc.x + loc.width < uniqueLoc.x || 
                     loc.y > uniqueLoc.y + uniqueLoc.height || 
                     loc.y + loc.height < uniqueLoc.y);
        });
        if (!isOverlapping) {
            uniqueLocations.push(loc);
        }
    });
    return uniqueLocations;
"""

JS_GET_INTERACTIVE_ELEMENTS = """
    // ... (This script is now a fallback, but kept for LABEL mode)
    const elements = Array.from(document.querySelectorAll('a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'));
    const interactiveElements = []; let labelCounter = 1;
    for (const elem of elements) {
        const rect = elem.getBoundingClientRect();
        if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0 && rect.bottom <= window.innerHeight && rect.right <= window.innerWidth) {
            elem.setAttribute('data-magic-agent-label', labelCounter);
            interactiveElements.push({label: labelCounter, x: rect.left, y: rect.top, width: rect.width, height: rect.height});
            labelCounter++;
        }
    }
    return interactiveElements;
"""

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You receive a screenshot and issue commands in JSON to accomplish a user's goal.

--- PRIMARY WORKFLOW: TEXT-BASED INTERACTION ---

Your main strategy is a two-step process to click on text:

1.  **`FIND_TEXT`**: First, you identify the text you want to click on the screen and use the `FIND_TEXT` command.
    - **Example:** `{"command": "FIND_TEXT", "params": {"text": "Sign In"}, "thought": "I need to sign in. I'll find the 'Sign In' button.", "speak": "Looking for the sign-in button."}`

2.  **`CLICK_FOUND_TEXT` (If Necessary)**:
    - If the system finds **only one** instance of your text, it will click it automatically and show you the result on the next screen. You don't need to do anything.
    - If the system finds **multiple** instances of your text (e.g., several "Details" buttons), the next screenshot will show a red numbered label next to each one. You must then use the `CLICK_FOUND_TEXT` command with the correct number.
    - **Example:** `{"command": "CLICK_FOUND_TEXT", "params": {"label": 2}, "thought": "The second 'Details' button is the one I want. I'll click label 2.", "speak": "Clicking the second option."}`

--- FALLBACK MODES (Use only when necessary) ---

If you cannot click something using the `FIND_TEXT` workflow, you can switch to a fallback mode for one action, then you should switch back to TEXT mode.

*   **LABEL Mode**: For clicking icons or elements without text.
    1.  Issue `SWITCH_TO_LABEL_MODE`.
    2.  On the next turn, you'll see a screenshot with numbers on all clickable items.
    3.  Issue `CLICK` with the number you want (e.g., `{"command": "CLICK", "params": {"label": 5}}`).
    4.  Issue `SWITCH_TO_TEXT_MODE` to return to normal.

*   **GRID Mode**: For clicking a specific point on the screen (e.g., a map, a CAPTCHA checkbox).
    1.  Issue `SWITCH_TO_GRID_MODE`.
    2.  On the next turn, you'll see a grid.
    3.  Issue `GRID_CLICK` with the coordinate (e.g., `{"command": "GRID_CLICK", "params": {"cell": "D10"}}`).
    4.  Issue `SWITCH_TO_TEXT_MODE` to return to normal.

--- GUIDING PRINCIPLES ---

1.  **MASTER THE `FIND_TEXT` WORKFLOW:** This is your primary tool. Use it for almost everything.
2.  **SCROLL:** Pages are long. Always scroll down to see all content before making a decision. Use the `SCROLL` command.
3.  **SEARCH:** Use `CUSTOM_SEARCH` to search the web via "Bing".
4.  **BE PATIENT:** Some actions, like finding text and clicking, are now multi-step. Follow the process.

--- COMMAND REFERENCE ---

**== PRIMARY TEXT INTERACTION COMMANDS ==**
1.  **`FIND_TEXT`**: Finds all occurrences of text on the page to prepare for a click.
    - **Params:** `{"text": "<text_to_find>"}`
2.  **`CLICK_FOUND_TEXT`**: (Only if prompted) Clicks one of the numbered text locations from a previous `FIND_TEXT` command.
    - **Params:** `{"label": <int>}`

**== OTHER INTERACTION COMMANDS ==**
3.  **`TYPE`**: Types text. You MUST click an input field first using the `FIND_TEXT` workflow.
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`
4.  **`SCROLL`**: Scrolls the page.
    - **Params:** `{"direction": "<up|down>"}`

**== MODE SWITCHING & FALLBACKS ==**
5.  **`SWITCH_TO_LABEL_MODE`**: Switches to label-based clicking for elements without text.
6.  **`CLICK`**: (LABEL MODE ONLY) Clicks an element by its number.
7.  **`SWITCH_TO_GRID_MODE`**: Switches to grid-based clicking for precision.
8.  **`GRID_CLICK`**: (GRID MODE ONLY) Clicks a grid cell.
9.  **`SWITCH_TO_TEXT_MODE`**: Switches back to the default `FIND_TEXT` workflow.

**== NAVIGATION & BROWSER ==**
10. `START_BROWSER`, `END_BROWSER`, `NAVIGATE`, `CUSTOM_SEARCH`, `GO_BACK`

**== USER INTERACTION ==**
11. `PAUSE_AND_ASK`, `SPEAK`
"""

# ... (send_whatsapp_message and send_whatsapp_image functions remain the same)
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
            "user_dir": user_dir, "labeled_elements": {}, "found_text_locations": [],
            "tab_handles": {}, "is_processing": False, "interaction_mode": "TEXT",
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
        session["driver"] = driver; session["mode"] = "BROWSER"; session["interaction_mode"] = "TEXT"
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc()
        return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["found_text_locations"] = []
    session["tab_handles"] = {}; session["interaction_mode"] = "TEXT"

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    try:
        # Get tab info
        window_handles = driver.window_handles; current_handle = driver.current_window_handle; tabs = []
        session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1; session["tab_handles"][tab_id] = handle; driver.switch_to.window(handle)
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e: print(f"Could not get tab info: {e}"); return None, "", ""
    
    try:
        # Take screenshot and prepare to draw
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image, "RGBA")
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=18)
        except IOError: font = ImageFont.load_default()

        context_info_text = ""
        mode = session["interaction_mode"]

        if mode == "RESOLVE_TEXT":
            print("Capturing state in RESOLVE_TEXT mode.")
            context_info_text = "Multiple locations found. Use CLICK_FOUND_TEXT with the correct number."
            for i, loc in enumerate(session["found_text_locations"]):
                label = i + 1
                x, y, w, h = loc['x'], loc['y'], loc['width'], loc['height']
                draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
                draw.rectangle([x, y-22, x + 25, y], fill=(0, 0, 0, 128))
                draw.text((x + 5, y - 20), str(label), fill="white", font=font)
        
        elif mode == "GRID":
            print("Capturing state in GRID mode.")
            context_info_text = "Current Mode: GRID. Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
            cols = image.width // GRID_CELL_SIZE
            rows = image.height // GRID_CELL_SIZE
            for i in range(rows):
                for j in range(cols):
                    x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE; label = f"{chr(ord('A')+j)}{i+1}"
                    draw.rectangle([x1+2, y1+2, x1 + 35, y1 + 22], fill=(0, 0, 0, 128))
                    draw.text((x1 + 4, y1 + 4), label, fill="white", font=font)
                    draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")

        elif mode == "LABEL":
            print("Capturing state in LABEL mode.")
            elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
            session["labeled_elements"] = {el['label']: el for el in elements}
            context_info_text = "Current Mode: LABEL. Use CLICK with a number."
            for label, el in session["labeled_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
                draw.rectangle([x, y-22, x + 25, y], fill=(0, 0, 0, 128))
                draw.text((x + 5, y - 20), str(label), fill="white", font=font)
        else: # Default TEXT mode
             print("Capturing state in TEXT mode (no overlays).")
             context_info_text = "Current Mode: TEXT. Use FIND_TEXT to click on elements."

        image.save(screenshot_path)
        print(f"State captured in {mode} mode.")
        return screenshot_path, context_info_text, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, "", tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    # ... (AI calling logic remains the same)
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
    screenshot_path, context_info_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{context_info_text}\n\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "Could not get a view of the page. I will close the browser."); close_browser(session)

def click_at_coords(driver, x, y, w, h):
    """Uses ActionChains to click the center of a given coordinate box."""
    center_x = x + w / 2
    center_y = y + h / 2
    print(f"Performing precision click at viewport coordinates ({center_x:.2f}, {center_y:.2f})")
    # ActionChains can be weird with offsets. A direct JS click is often more reliable.
    # However, we will use a move and click to better simulate a user.
    ActionChains(driver).move_by_offset(center_x, center_y).click().perform()
    # IMPORTANT: Reset the offset back to (0,0) for the next action
    ActionChains(driver).move_by_offset(-center_x, -center_y).perform()


def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    
    # ... (interrupt/stop logic remains the same)
    if session.get("stop_requested"):
        print("Stop was requested, ignoring AI command."); session["stop_requested"] = False; session["chat_history"] = []; return
    if session.get("interrupt_requested"):
        print("Interrupt was requested, ignoring AI command."); session["interrupt_requested"] = False; return

    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, "I received an invalid response from my AI module. Ending task.")
        if session["mode"] == "BROWSER": close_browser(session)
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought} | Mode: {session['interaction_mode']}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    driver = session.get("driver")
    
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER"]:
        send_whatsapp_message(from_number, "The browser was closed. I'm starting it up..."); driver = start_browser(session)
        if not driver: send_whatsapp_message(from_number, "Failed to restart browser."); close_browser(session); return
        time.sleep(1); process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        next_step_caption = f"Action done: {command}"

        if command == "FIND_TEXT":
            text_to_find = params.get("text")
            if not text_to_find:
                send_whatsapp_message(from_number, "FIND_TEXT failed: No text provided.")
                action_was_performed = False
            else:
                locations = driver.execute_script(JS_FIND_TEXT_LOCATIONS, text_to_find)
                if not locations:
                    send_whatsapp_message(from_number, f"I couldn't find any text matching '{text_to_find}'.")
                    action_was_performed = False
                    next_step_caption = f"Action Failed: Could not find '{text_to_find}'."
                elif len(locations) == 1:
                    send_whatsapp_message(from_number, f"Found one match for '{text_to_find}'. Clicking it now.")
                    click_at_coords(driver, locations[0]['x'], locations[0]['y'], locations[0]['width'], locations[0]['height'])
                    next_step_caption = f"Clicked the unique instance of '{text_to_find}'."
                else:
                    send_whatsapp_message(from_number, f"I found {len(locations)} matches for '{text_to_find}'. Please choose one.")
                    session["found_text_locations"] = locations
                    session["interaction_mode"] = "RESOLVE_TEXT"
                    next_step_caption = f"Multiple matches found for '{text_to_find}'. Please resolve."
        
        elif command == "CLICK_FOUND_TEXT":
            label = params.get("label")
            if session["interaction_mode"] != "RESOLVE_TEXT" or not isinstance(label, int) or not (1 <= label <= len(session["found_text_locations"])):
                send_whatsapp_message(from_number, f"Invalid CLICK_FOUND_TEXT command.")
                action_was_performed = False
            else:
                loc = session["found_text_locations"][label - 1]
                click_at_coords(driver, loc['x'], loc['y'], loc['width'], loc['height'])
                session["interaction_mode"] = "TEXT" # Return to default mode
                session["found_text_locations"] = [] # Clear the locations
                next_step_caption = f"Clicked on text match #{label}."

        elif command == "SWITCH_TO_GRID_MODE": session["interaction_mode"] = "GRID"
        elif command == "SWITCH_TO_LABEL_MODE": session["interaction_mode"] = "LABEL"
        elif command == "SWITCH_TO_TEXT_MODE": session["interaction_mode"] = "TEXT"
        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "CLICK":
            label = params.get("label"); element_info = session["labeled_elements"].get(label)
            if session["interaction_mode"] != "LABEL" or not element_info:
                action_was_performed = False
            else: click_at_coords(driver, element_info['x'], element_info['y'], element_info['width'], element_info['height'])
        elif command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if session["interaction_mode"] != "GRID" or not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                 action_was_performed = False
            else:
                col_index = ord(cell[0]) - ord('A'); row_index = int(cell[1:]) - 1
                x = col_index * GRID_CELL_SIZE; y = row_index * GRID_CELL_SIZE
                click_at_coords(driver, x, y, GRID_CELL_SIZE, GRID_CELL_SIZE)

        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {800 if params.get('direction', 'down') == 'down' else -800});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command in ["PAUSE_AND_ASK", "SPEAK"]: return
        else: print(f"Unknown command: {command}"); send_whatsapp_message(from_number, f"Unknown command '{command}'.");
        
        if action_was_performed: time.sleep(2); process_next_browser_step(from_number, session, next_step_caption)
        else: # If action failed, get current state immediately to let AI recover
            time.sleep(1); process_next_browser_step(from_number, session, caption=f"The last action ({command}) failed. Please assess the screen and try a different approach.")

    except Exception as e:
        error_summary = f"Error during command '{command}': {e}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, f"An action failed unexpectedly. I will show the AI what happened so it can recover.")
        time.sleep(1)
        process_next_browser_step(from_number, session, caption=f"A critical error occurred: {error_summary}. What should I do now?")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # ... (Webhook logic remains the same)
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
                print(f"User {from_number} issued /stop command."); session["stop_requested"] = True; close_browser(session)
                session["is_processing"] = False; send_whatsapp_message(from_number, "Request stopped. Your task has been cancelled."); return Response(status=200)

            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                if session["mode"] != "BROWSER": send_whatsapp_message(from_number, "No browser task to interrupt.")
                else: session["interrupt_requested"] = True; session["is_processing"] = False; send_whatsapp_message(from_number, "Interrupted. What would you like to do instead?")
                return Response(status=200)

            if command_text == "/clear":
                print(f"User {from_number} issued /clear command."); close_browser(session)
                if from_number in user_sessions: del user_sessions[from_number]
                send_whatsapp_message(from_number, "Your session and chat history have been cleared."); print(f"Session for {from_number} cleared."); return Response(status=200)

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "Please wait, I'm working. Use /interrupt to stop the current action or /stop to end the task."); return Response(status=200)
            
            try:
                session["is_processing"] = True
                session["chat_history"].append({"role": "user", "parts": [user_message_text]})

                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=f"The user's initial request is: '{user_message_text}'. Start the task.")
                    process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    process_next_browser_step(from_number, session, f"Continuing with new instructions: {user_message_text}")
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
