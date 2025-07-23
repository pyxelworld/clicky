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
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.actions.action_builder import ActionBuilder
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
GRID_CELL_SIZE = 80 # The size of each grid cell in pixels for grid mode

# --- JAVASCRIPT FOR ELEMENT LABELING (ADDS A DATA ATTRIBUTE) ---
JS_GET_INTERACTIVE_ELEMENTS = """
    const elements = Array.from(document.querySelectorAll(
        'a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'
    ));
    const interactiveElements = [];
    let labelCounter = 1;
    // Clear previous labels to avoid confusion on re-renders
    document.querySelectorAll('[data-magic-agent-label]').forEach(el => el.removeAttribute('data-magic-agent-label'));
    for (let i = 0; i < elements.length; i++) {
        const elem = elements[i];
        const rect = elem.getBoundingClientRect();
        if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)) {
            
            elem.setAttribute('data-magic-agent-label', labelCounter);

            let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || elem.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').substring(0, 50);
            interactiveElements.push({
                label: labelCounter,
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
                tag: elem.tagName.toLowerCase(),
                text: text
            });
            labelCounter++;
        }
    }
    return interactiveElements;
"""

JS_FIND_ELEMENTS_IN_RECT = """
// arguments: [x1, y1, x2, y2]
const [x1, y1, x2, y2] = arguments;
const elements = Array.from(document.querySelectorAll('a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'));
const foundElements = [];
// Clear previous temporary markers
document.querySelectorAll('[data-magic-agent-found]').forEach(el => el.removeAttribute('data-magic-agent-found'));
for (let i = 0; i < elements.length; i++) {
    const elem = elements[i];
    const rect = elem.getBoundingClientRect();
    // Check if the center of the element is within the rectangle
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    if (rect.width > 0 && rect.height > 0 && // Element must be visible
        centerX >= x1 && centerX <= x2 &&
        centerY >= y1 && centerY <= y2 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth) &&
        rect.top >= 0 && rect.left >= 0)
    {
        const uniqueId = `magic-agent-found-${i}`;
        elem.setAttribute('data-magic-agent-found', uniqueId);
        foundElements.push({
            id: uniqueId,
            x: rect.left,
            y: rect.top,
            width: rect.width,
            height: rect.height,
            tag: elem.tagName.toLowerCase(),
            text: (elem.innerText || elem.value || elem.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').substring(0, 50)
        });
    }
}
return foundElements;
"""

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You operate by receiving a state (a screenshot and tab info) and issuing a single command in JSON format.

--- ERROR RECOVERY ---
If you are told that a command failed, the page may have changed unexpectedly or the command was invalid. Analyze the new screenshot and the error message provided. Do not repeat the failed command. Instead, assess the situation and issue a new command to recover or proceed. For example, if a click failed, the element might not exist anymore; look for an alternative.

--- INTERACTION MODES ---

You operate in one of two modes: GRID mode or LABEL mode. You must manage switching between them.

1.  **GRID Mode (Default & Precision Clicks):** This is your primary mode. The screenshot is overlaid with a coordinate grid (A1, B2, etc.). Use the `GRID_CLICK` command.
    - If there's **one** interactive element in the cell you choose, it will be clicked.
    - If there are **multiple** elements, the view will **automatically zoom in** on that cell, showing a new, finer grid. You must then issue a new `GRID_CLICK` command with a cell from this "zoomed grid" to select the specific item.
    - If there are **no** elements, it will click the center of the cell.
2.  **LABEL Mode:** If you find the grid too distracting for a simple task like filling a form, you can switch to this mode. The screenshot will have red numbers on interactive elements. Use the `CLICK` command with the element's number.

--- GUIDING PRINCIPLES ---

1.  **MODE SWITCHING STRATEGY:** Your default is GRID mode. If you need to see element labels for clarity (e.g., complex forms), issue `SWITCH_TO_LABEL_MODE`. Once done, immediately issue `SWITCH_TO_GRID_MODE` to return to the default.

2.  **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down on a page after it loads or after an action. The initial view is only the top of the page. You must scroll to understand the full context.

3.  **SEARCH STRATEGY:** To search the web, you MUST use the `CUSTOM_SEARCH` command with our "Bing" search engine. Do NOT use `NAVIGATE` to go to other search engines.

4.  **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt to fill it in. Stop and ask the user for permission using the `PAUSE_AND_ASK` command. Follow the same if you are asked a verification code or other.

5.  **SHOPPING STRATEGY:** When asked to shop, first use `PAUSE_AND_ASK` to clarify the exact product and price range. Then, on shopping sites, use sorting/filtering features to meet the user's criteria.

6.  **HANDLING OBSTACLES (CAPTCHA):** If you land on a page with a standard CAPTCHA, use `GRID_CLICK` on the checkbox. If it's a more complex "select all images" CAPTCHA, you cannot solve it. Use the `GO_BACK` command and choose a different search result.

--- YOUR RESPONSE FORMAT ---

Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

**== MODE SWITCHING COMMANDS ==**
1.  **`SWITCH_TO_GRID_MODE`**: Switches to the default grid-based clicking. The next screenshot will have a grid.
    - **Params:** `{}`
2.  **`SWITCH_TO_LABEL_MODE`**: Switches to label-based clicking for tasks like filling out forms.
    - **Params:** `{}`

**== BROWSER START/STOP COMMANDS ==**
3.  **`START_BROWSER`**: Initiates a new browser session. Starts in GRID mode.
    - **Params:** `{}`
4.  **`END_BROWSER`**: Closes the browser when the task is fully complete.
    - **Params:** `{"reason": "<summary>"}`

**== NAVIGATION COMMANDS ==**
5.  **`NAVIGATE`**: Goes directly to a URL.
    - **Params:** `{"url": "<full_url>"}`
6.  **`CUSTOM_SEARCH`**: Performs a search using "Bing".
    - **Params:** `{"query": "<search_term>"}`
7.  **`GO_BACK`**: Navigates to the previous page in history.
    - **Params:** `{}`

**== PAGE INTERACTION COMMANDS ==**
8.  **`CLICK`**: (LABEL MODE ONLY) Clicks an element identified by its label number.
    - **Params:** `{"label": <int>}`
9.  **`GRID_CLICK`**: (GRID or ZOOMED_GRID MODE)
    - In **GRID mode**, this attempts to click an element within the specified cell.
    - If there are **multiple** elements, the view will auto-zoom, presenting a new, finer "zoomed grid". You must then issue a new `GRID_CLICK` command with a cell from this new grid.
    - **Params:** `{"cell": "<e.g., 'C5', 'G12'>"}`
    - **Example:** `{"command": "GRID_CLICK", "params": {"cell": "D10"}, "thought": "The 'Continue' button is in cell D10. I will now click it.", "speak": "Clicking D10."}`
10. **`TYPE`**: Types text. You MUST `CLICK` or `GRID_CLICK` an input field first.
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`
11. **`CLEAR`**: (LABEL MODE ONLY) Clears text from an input field.
    - **Params:** `{"label": <int>}`
12. **`SCROLL`**: Scrolls the page.
    - **Params:** `{"direction": "<up|down>"}`

**== TAB MANAGEMENT COMMANDS ==**
13. **`NEW_TAB`**, **`SWITCH_TO_TAB`**, **`CLOSE_TAB`**

**== USER INTERACTION COMMANDS ==**
14. **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
    - **Params:** `{"question": "<your_question>"}`
15. **`SPEAK`**: For simple conversation.
    - **Params:** `{"text": "<your_response>"}`
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
            "user_dir": user_dir, "labeled_elements": {}, "tab_handles": {},
            "is_processing": False, "interaction_mode": "GRID",
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
        session["driver"] = driver; session["mode"] = "BROWSER"; session["interaction_mode"] = "GRID"
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
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}
    session["tab_handles"] = {}; session["interaction_mode"] = "GRID"

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    try:
        window_handles = driver.window_handles; current_handle = driver.current_window_handle; tabs = []
        session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1; session["tab_handles"][tab_id] = handle; driver.switch_to.window(handle)
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e: print(f"Could not get tab info: {e}"); return None, "", ""
    
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        font_size = 22
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=font_size)
        except IOError: font = ImageFont.load_default(size=font_size)

        labels_text = ""
        interaction_mode = session.get("interaction_mode", "GRID")

        if interaction_mode == "GRID":
            print("Capturing state in GRID mode.")
            labels_text = "GRID MODE: Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
            cols = min(image.width // GRID_CELL_SIZE, 16) # Cap columns at P
            rows = image.height // GRID_CELL_SIZE
            for i in range(rows):
                for j in range(cols):
                    x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                    draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")
                    label = f"{chr(ord('A')+j)}{i+1}"
                    draw.text((x1 + 4, y1 + 4), label, fill="red", font=font)
        
        elif interaction_mode == "ZOOMED_GRID":
            print("Capturing state in ZOOMED_GRID mode.")
            zoom_box = session['zoom_box']
            zoomed_elements = session['zoomed_elements']
            sub_cols, sub_rows = 4, 4
            zoom_width = zoom_box['x2'] - zoom_box['x1']
            zoom_height = zoom_box['y2'] - zoom_box['y1']
            sub_cell_width = zoom_width / sub_cols
            sub_cell_height = zoom_height / sub_rows
            labels_text = "ZOOMED GRID: Multiple items found. Select a cell to click the item inside.\n"
            draw.rectangle([zoom_box['x1'], zoom_box['y1'], zoom_box['x2'], zoom_box['y2']], outline="yellow", width=4)
            
            sub_grid_map = {}
            for i in range(sub_rows):
                for j in range(sub_cols):
                    sx1 = zoom_box['x1'] + j * sub_cell_width; sy1 = zoom_box['y1'] + i * sub_cell_height
                    sx2 = sx1 + sub_cell_width; sy2 = sy1 + sub_cell_height
                    draw.rectangle([sx1, sy1, sx2, sy2], outline="rgba(255,255,0,128)")
                    label = f"{chr(ord('A')+j)}{i+1}"
                    
                    for el in zoomed_elements:
                        el_center_x = el['x'] + el['width'] / 2; el_center_y = el['y'] + el['height'] / 2
                        if sx1 <= el_center_x < sx2 and sy1 <= el_center_y < sy2:
                            if label not in sub_grid_map: # Map first element found in cell
                                sub_grid_map[label] = el
                                draw.text((sx1 + 2, sy1 + 2), label, fill="yellow", font=font)
                                labels_text += f"  {label}: {el['tag']} '{el['text']}'\n"
                                break
            session['sub_grid_map'] = sub_grid_map

        else: # LABEL mode
            print("Capturing state in LABEL mode.")
            elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
            session["labeled_elements"] = {el['label']: el for el in elements}
            labels_text = "Interactive Elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
            for label, el in session["labeled_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                label_str = str(label)
                text_bbox = draw.textbbox((0,0), label_str, font=font)
                text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
                padding = 4
                
                draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
                draw.rectangle([x, y, x + text_w + padding*2, y + text_h + padding*2], fill="red")
                draw.text((x + padding, y + padding), label_str, fill="white", font=font)
        
        image.save(screenshot_path)
        print(f"State captured in {interaction_mode} mode.")
        return screenshot_path, labels_text, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
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

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    
    if session.get("stop_requested"):
        print("Stop was requested, ignoring AI command."); session["stop_requested"] = False; session["chat_history"] = []; return
    if session.get("interrupt_requested"):
        print("Interrupt was requested, ignoring AI command."); session["interrupt_requested"] = False; return

    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        if session["mode"] == "BROWSER": close_browser(session)
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought} | Mode: {session['interaction_mode']}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    driver = session.get("driver")
    
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER"]:
        send_whatsapp_message(from_number, "The browser was closed. I'm starting it up to continue your task...")
        driver = start_browser(session)
        if not driver: send_whatsapp_message(from_number, "I failed to restart the browser."); close_browser(session); return
        time.sleep(1); process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        if command == "SWITCH_TO_GRID_MODE":
            session["interaction_mode"] = "GRID"
        elif command == "SWITCH_TO_LABEL_MODE":
            session["interaction_mode"] = "LABEL"
        elif command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                send_whatsapp_message(from_number, f"Invalid cell format: {cell}."); action_was_performed = False
            
            elif session["interaction_mode"] == "ZOOMED_GRID":
                element_to_click = session.get('sub_grid_map', {}).get(cell)
                if not element_to_click:
                    send_whatsapp_message(from_number, f"Cell {cell} is empty or invalid in the zoomed grid. Please try again.")
                    action_was_performed = False
                else:
                    driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-found="{element_to_click["id"]}"]').click()
                    session["interaction_mode"] = "GRID" # Reset to default
                    for key in ["zoom_box", "zoomed_elements", "sub_grid_map"]: session.pop(key, None)
            
            elif session["interaction_mode"] == "GRID":
                col_index = ord(cell[0]) - ord('A'); row_index = int(cell[1:]) - 1
                x1, y1 = col_index * GRID_CELL_SIZE, row_index * GRID_CELL_SIZE
                x2, y2 = x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE
                
                found_elements = driver.execute_script(JS_FIND_ELEMENTS_IN_RECT, x1, y1, x2, y2)
                
                if len(found_elements) == 0:
                    send_whatsapp_message(from_number, f"No item in {cell}. Clicking its center.")
                    driver.execute_script(f"document.elementFromPoint({x1 + GRID_CELL_SIZE/2}, {y1 + GRID_CELL_SIZE/2}).click();")
                elif len(found_elements) == 1:
                    send_whatsapp_message(from_number, f"One item in {cell}. Clicking it.")
                    driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-found="{found_elements[0]["id"]}"]').click()
                else:
                    send_whatsapp_message(from_number, f"{len(found_elements)} items in {cell}. Zooming in.")
                    session["interaction_mode"] = "ZOOMED_GRID"
                    session["zoom_box"] = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
                    session["zoomed_elements"] = found_elements
            else:
                send_whatsapp_message(from_number, "Error: GRID_CLICK can't be used in LABEL mode.")
                action_was_performed = False

        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
            process_next_browser_step(from_number, session, "Browser started. What's next?")
            return
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "NEW_TAB": driver.switch_to.new_window('tab'); driver.get(params["url"]) if "url" in params and params["url"] else None
        elif command == "CLOSE_TAB":
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
            else: send_whatsapp_message(from_number, "I can't close the last tab."); action_was_performed = False
        elif command == "SWITCH_TO_TAB":
            handle = session["tab_handles"].get(params.get("tab_id"))
            if handle: driver.switch_to.window(handle)
            else: send_whatsapp_message(from_number, "I couldn't find that tab ID."); action_was_performed = False
        elif command == "CLICK":
            if session["interaction_mode"] != "LABEL":
                send_whatsapp_message(from_number, "Error: Cannot use CLICK in GRID mode."); action_was_performed = False
            else:
                label = params.get("label")
                if not session["labeled_elements"].get(label): send_whatsapp_message(from_number, f"Label {label} not valid."); action_was_performed = False
                else:
                    try: driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]').click()
                    except Exception as e: print(f"Click failed: {e}"); send_whatsapp_message(from_number, "Click failed.")
        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "CLEAR":
            if session["interaction_mode"] != "LABEL":
                send_whatsapp_message(from_number, "Error: Cannot use CLEAR in GRID mode."); action_was_performed = False
            else:
                label = params.get("label")
                element_to_clear = driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]')
                element_to_clear.send_keys(Keys.CONTROL + "a"); element_to_clear.send_keys(Keys.DELETE)
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
        session["interaction_mode"] = "GRID" # Reset to default grid on error
        for key in ["zoom_box", "zoomed_elements", "sub_grid_map"]: session.pop(key, None)
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
