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
AI_MODEL_NAME = "gemini-2.0-flash" # Changed to a more recent model if available

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
GRID_CELL_SIZE = 80  # Increased for fewer, larger grids
SUB_GRID_COLUMNS = 22 # For the "zoom-in" grid, up to 'V'

# --- JAVASCRIPT SNIPPETS ---
JS_GET_INTERACTIVE_ELEMENTS = """
    // ... (This JS is used for LABEL mode)
    const elements = Array.from(document.querySelectorAll(
        'a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'
    ));
    const interactiveElements = [];
    let labelCounter = 1;
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

JS_GET_ELEMENTS_IN_RECT = """
    // This new JS is for the smart GRID_CLICK feature
    const [x, y, width, height] = arguments;
    const elements = Array.from(document.querySelectorAll(
        'a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'
    ));
    const foundElements = [];
    const targetRect = { left: x, top: y, right: x + width, bottom: y + height };

    for (let i = 0; i < elements.length; i++) {
        const elem = elements[i];
        const rect = elem.getBoundingClientRect();
        
        // Check for intersection between element and the grid cell
        const intersects = !(rect.right < targetRect.left || 
                             rect.left > targetRect.right || 
                             rect.bottom < targetRect.top || 
                             rect.top > targetRect.bottom);

        if (intersects && rect.width > 0 && rect.height > 0) {
             let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || '').trim().replace(/\\s+/g, ' ').substring(0, 50);
             // Ensure the element has a label for easy clicking
             if (!elem.hasAttribute('data-magic-agent-label')) {
                 elem.setAttribute('data-magic-agent-label', `grid-click-${i}`);
             }
             foundElements.push({
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                tag: elem.tagName.toLowerCase(),
                text: text,
                label: elem.getAttribute('data-magic-agent-label')
             });
        }
    }
    return foundElements;
"""

# --- SYSTEM PROMPT (UPDATED FOR GRID-DEFAULT) ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You operate by receiving a state (a screenshot and tab info) and issuing a single command in JSON format.

--- ERROR RECOVERY ---
If you are told that a command failed, the page may have changed unexpectedly or the command was invalid. Analyze the new screenshot and the error message provided. Do not repeat the failed command. Instead, assess the situation and issue a new command to recover or proceed. For example, if a click failed, the element might not exist anymore; look for an alternative.

--- INTERACTION MODES ---

You operate in one of two modes: GRID mode or LABEL mode. You must manage switching between them.

1.  **GRID Mode (Default):** The screenshot will be overlaid with a coordinate grid (A1, B2, C3, etc.). This is your primary mode of operation. Use the `GRID_CLICK` command with the cell coordinate (e.g., 'C5'). If a grid cell contains multiple clickable items, the system may automatically ask you for a more specific location in a zoomed-in grid.
2.  **LABEL Mode:** If you need to see all interactive elements clearly numbered, you must switch to this mode using `SWITCH_TO_LABEL_MODE`. The screenshot will have red numbers on all detected interactive elements. Use the `CLICK` command with the element's number. After using it, switch back to GRID mode with `SWITCH_TO_GRID_MODE`.

--- GUIDING PRINCIPLES ---

1.  **MODE SWITCHING STRATEGY:** Start and stay in GRID mode. Only switch to LABEL mode if you absolutely cannot identify an element's position on the grid. After you are done with LABEL mode, immediately issue `SWITCH_TO_GRID_MODE` to return to normal operation.

2.  **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down on a page after it loads or after an action. The initial view is only the top of the page. You must scroll to understand the full context.

3.  **SEARCH STRATEGY:** To search the web, you MUST use the `CUSTOM_SEARCH` command with our "Bing" search engine. Do NOT use `NAVIGATE` to go to other search engines.

4.  **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt to fill it in. Stop and ask the user for permission using the `PAUSE_AND_ASK` command. Follow the same if you are asked a verification code or other.

5.  **SHOPPING STRATEGY:** When asked to shop, first use `PAUSE_AND_ASK` to clarify the exact product and price range. Then, on shopping sites, use sorting/filtering features to meet the user's criteria.

6.  **HANDLING OBSTACLES (CAPTCHA):** If you land on a page with a standard CAPTCHA, use `GRID_CLICK` on the checkbox. If it's a more complex "select all images" CAPTCHA, you cannot solve it. Use the `GO_BACK` command and choose a different search result.

--- YOUR RESPONSE FORMAT ---

Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

**== MODE SWITCHING COMMANDS ==**

1.  **`SWITCH_TO_GRID_MODE`**: Switches back to the default grid-based clicking.
    - **Params:** `{}`

2.  **`SWITCH_TO_LABEL_MODE`**: Switches to numbered-label clicking for when the grid is ambiguous.
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

8.  **`GRID_CLICK`**: (GRID MODE ONLY) Clicks within a specified grid cell. The system will handle clicking the correct element or ask for clarification if needed.
    - **Params:** `{"cell": "<e.g., 'C5', 'G12'>"}`

9.  **`CLICK`**: (LABEL MODE ONLY) Clicks an element identified by its label number.
    - **Params:** `{"label": <int>}`

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
            "is_processing": False, "interaction_mode": "GRID",  # Default to GRID
            "stop_requested": False, "interrupt_requested": False,
            "awaiting_sub_grid_choice": False # For the new smart grid feature
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
        session["driver"] = driver; session["mode"] = "BROWSER"; session["interaction_mode"] = "GRID" # Default to GRID
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
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}
    session["tab_handles"] = {}; session["interaction_mode"] = "GRID" # Reset to GRID
    session["awaiting_sub_grid_choice"] = False

def draw_clear_text(draw, pos, text, font, background_color="rgba(0,0,0,180)"):
    """Draws text with a semi-transparent background for clarity."""
    try:
        # Use textbbox for more accurate positioning
        text_bbox = draw.textbbox(pos, text, font=font)
        # Add a small padding for the background
        bg_bbox = (text_bbox[0] - 2, text_bbox[1] - 2, text_bbox[2] + 2, text_bbox[3] + 2)
        draw.rectangle(bg_bbox, fill=background_color)
        draw.text(pos, text, fill="white", font=font)
    except AttributeError: # Fallback for older PIL versions
        draw.text(pos, text, fill="red", font=font)

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
        draw = ImageDraw.Draw(image, "RGBA")
        try: 
            font_label = ImageFont.truetype("DejaVuSans-Bold.ttf", size=20)
            font_grid = ImageFont.truetype("DejaVuSans.ttf", size=16)
        except IOError: 
            font_label = ImageFont.load_default(size=20)
            font_grid = ImageFont.load_default(size=16)

        labels_text = ""
        if session["interaction_mode"] == "GRID":
            print("Capturing state in GRID mode.")
            labels_text = "GRID MODE: Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
            cols = image.width // GRID_CELL_SIZE
            rows = image.height // GRID_CELL_SIZE
            for i in range(rows):
                for j in range(cols):
                    x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                    draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")
                    label = f"{chr(ord('A')+j)}{i+1}"
                    draw_clear_text(draw, (x1 + 3, y1 + 3), label, font_grid)
        else: # LABEL mode
            print("Capturing state in LABEL mode.")
            elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
            session["labeled_elements"] = {el['label']: el for el in elements}
            labels_text = "Interactive Elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
            for label, el in session["labeled_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
                draw_clear_text(draw, (x + 2, y + 2), str(label), font_label)
        
        image.convert("RGB").save(screenshot_path)
        print(f"State captured in {session['interaction_mode']} mode.")
        return screenshot_path, labels_text, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, "", tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append(Image.open(image_path))
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: {e}"}, "thought": "Image read failed.", "speak": "Error with screen view."})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt_parts, generation_config=genai.types.GenerationConfig(response_mime_type="application/json"))
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
    
    if session.get("stop_requested") or session.get("interrupt_requested"):
        print("Stop or interrupt was requested, ignoring AI command.")
        session["stop_requested"] = False; session["interrupt_requested"] = False
        if not session.get("stop_requested"): session["chat_history"] = []
        return

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
            if session["interaction_mode"] != "GRID":
                send_whatsapp_message(from_number, "Error: Cannot use GRID_CLICK in LABEL mode.")
                action_was_performed = False
            else:
                cell = params.get("cell", "").upper()
                if not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                    send_whatsapp_message(from_number, f"Invalid cell format: {cell}."); action_was_performed = False
                else:
                    col_index = ord(cell[0]) - ord('A')
                    row_index = int(cell[1:]) - 1
                    rect_x, rect_y = col_index * GRID_CELL_SIZE, row_index * GRID_CELL_SIZE
                    
                    elements_in_cell = driver.execute_script(JS_GET_ELEMENTS_IN_RECT, rect_x, rect_y, GRID_CELL_SIZE, GRID_CELL_SIZE)
                    
                    if len(elements_in_cell) == 0:
                        print(f"No elements in cell {cell}. Clicking center.")
                        click_x, click_y = rect_x + (GRID_CELL_SIZE / 2), rect_y + (GRID_CELL_SIZE / 2)
                        driver.execute_script(f"document.elementFromPoint({click_x}, {click_y}).click();")
                    elif len(elements_in_cell) == 1:
                        element_label = elements_in_cell[0]['label']
                        print(f"One element in cell {cell}. Clicking element with label: {element_label}")
                        driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{element_label}"]').click()
                    else:
                        print(f"Multiple ({len(elements_in_cell)}) elements in cell {cell}. Creating sub-grid.")
                        # Take a fresh screenshot and crop it
                        png_data = driver.get_screenshot_as_png()
                        image = Image.open(io.BytesIO(png_data))
                        cropped_image = image.crop((rect_x, rect_y, rect_x + GRID_CELL_SIZE, rect_y + GRID_CELL_SIZE))
                        
                        # Draw sub-grid on the cropped image
                        draw = ImageDraw.Draw(cropped_image, "RGBA")
                        try: font_grid = ImageFont.truetype("DejaVuSans.ttf", size=14)
                        except IOError: font_grid = ImageFont.load_default(size=14)
                        
                        sub_cell_width = cropped_image.width / SUB_GRID_COLUMNS
                        sub_cell_height = sub_cell_width # Keep it square
                        rows = int(cropped_image.height // sub_cell_height)
                        
                        for i in range(rows):
                            for j in range(SUB_GRID_COLUMNS):
                                x1, y1 = j * sub_cell_width, i * sub_cell_height
                                draw.rectangle([x1, y1, x1 + sub_cell_width, y1 + sub_cell_height], outline="rgba(0,255,0,150)")
                                label = f"{chr(ord('A')+j)}{i+1}"
                                draw_clear_text(draw, (x1 + 2, y1 + 2), label, font_grid, "rgba(0,0,0,200)")
                        
                        sub_grid_path = session["user_dir"] / "sub_grid.png"
                        cropped_image.convert("RGB").save(sub_grid_path)
                        
                        # Store context and ask user
                        session["awaiting_sub_grid_choice"] = True
                        session["sub_grid_rect"] = {"x": rect_x, "y": rect_y, "width": GRID_CELL_SIZE, "height": GRID_CELL_SIZE}
                        
                        send_whatsapp_image(from_number, sub_grid_path, caption=f"I found multiple items in cell {cell}. Please choose a more specific location from this zoomed-in view.")
                        return # Pause execution and wait for user's sub-grid choice
        
        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
            process_next_browser_step(from_number, session, "Browser started in GRID mode. What's next?")
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
                else: driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]').click()
        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "CLEAR":
            if session["interaction_mode"] != "LABEL": send_whatsapp_message(from_number, "Error: Cannot use CLEAR in GRID mode."); action_was_performed = False
            else:
                element_to_clear = driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{params.get("label")}"]')
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

            if message_id in processed_message_ids: return Response(status=200)
            processed_message_ids.add(message_id)
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I only process text messages."); return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            command_text = user_message_text.strip().lower()
            if command_text == "/stop":
                print(f"User {from_number} issued /stop command.")
                session["stop_requested"] = True; close_browser(session); session["is_processing"] = False
                send_whatsapp_message(from_number, "Request stopped. Your current task has been cancelled.")
                return Response(status=200)
            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                if session["mode"] != "BROWSER": send_whatsapp_message(from_number, "No task to interrupt.")
                else:
                    session["interrupt_requested"] = True; session["is_processing"] = False
                    send_whatsapp_message(from_number, "Interrupted. What would you like to do instead?")
                return Response(status=200)
            if command_text == "/clear":
                print(f"User {from_number} issued /clear command.")
                close_browser(session)
                if from_number in user_sessions: del user_sessions[from_number]
                send_whatsapp_message(from_number, "Your session and chat history have been cleared.")
                return Response(status=200)
            
            # --- NEW: Handle sub-grid choice ---
            if session.get("awaiting_sub_grid_choice"):
                print(f"Handling sub-grid choice: {user_message_text}")
                try:
                    driver = session["driver"]
                    sub_cell = user_message_text.strip().upper()
                    if not sub_cell or not sub_cell[0].isalpha() or not sub_cell[1:].isdigit():
                        send_whatsapp_message(from_number, "That's not a valid coordinate (e.g., B4). Please try again.")
                        return Response(status=200)

                    sub_rect = session["sub_grid_rect"]
                    sub_cell_width = sub_rect["width"] / SUB_GRID_COLUMNS
                    sub_cell_height = sub_cell_width
                    
                    col_index = ord(sub_cell[0]) - ord('A')
                    row_index = int(sub_cell[1:]) - 1
                    
                    # Calculate click point relative to the viewport
                    click_x = sub_rect["x"] + (col_index * sub_cell_width) + (sub_cell_width / 2)
                    click_y = sub_rect["y"] + (row_index * sub_cell_height) + (sub_cell_height / 2)
                    
                    driver.execute_script(f"document.elementFromPoint({click_x}, {click_y}).click();")
                    send_whatsapp_message(from_number, f"Clicked at {sub_cell}.")
                    
                    # Reset the sub-grid state and continue
                    session["awaiting_sub_grid_choice"] = False
                    session["sub_grid_rect"] = None
                    time.sleep(2)
                    process_next_browser_step(from_number, session, "Sub-grid click completed. What's next?")
                except Exception as e:
                    send_whatsapp_message(from_number, f"Sorry, I had trouble with that selection. Let's try again from the main view.")
                    print(f"Error in sub-grid selection: {e}")
                    session["awaiting_sub_grid_choice"] = False
                    process_next_browser_step(from_number, session, "Sub-grid selection failed. Please re-evaluate the page.")
                finally:
                    return Response(status=200)
            # --- END NEW LOGIC ---

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "Please wait, I'm working. Use /interrupt or /stop."); return Response(status=200)
            
            try:
                session["is_processing"] = True
                session["chat_history"].append({"role": "user", "parts": [user_message_text]})
                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=user_message_text)
                    process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    process_next_browser_step(from_number, session, f"Continuing with new instructions: {user_message_text}")
            finally:
                if not session.get("interrupt_requested"): session["is_processing"] = False

        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server (Updated) ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
