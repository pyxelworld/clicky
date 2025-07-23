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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
AI_MODEL_NAME = "gemini-1.5-flash" # Updated model for better performance

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
GRID_CELL_SIZE = 100 # The size of each grid cell in pixels for grid mode (Larger for clarity)

# --- JAVASCRIPT FOR ELEMENT LABELING (ADDS A DATA ATTRIBUTE) ---
JS_GET_INTERACTIVE_ELEMENTS = """
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

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You operate by receiving a state (a screenshot and tab info) and issuing a single command in JSON format.

--- ERROR RECOVERY ---
If you are told that a command failed, the page may have changed unexpectedly or the command was invalid. Analyze the new screenshot and the error message provided. Do not repeat the failed command. Instead, assess the situation and issue a new command to recover or proceed. For example, if a text click failed, the text might be slightly different; try a shorter, more distinctive part of the text.

--- INTERACTION MODES ---

You operate in one of three modes. You must manage switching between them.

1.  **TEXT Mode (Default):** This is your primary mode. The screenshot you see is clean, without any overlays. You identify elements by their visible text.
    - **Use Command:** `TEXT_CLICK`
    - **Example:** If you see a button that says "Sign In", you would issue `{"command": "TEXT_CLICK", "params": {"text": "Sign In"}, ...}`.

2.  **LABEL Mode (Fallback):** You switch to this mode **only** when you need to click something that has no identifiable text (like an icon) or when text is ambiguous (multiple elements have the same text).
    - **To Enter:** Issue the `SWITCH_TO_LABEL_MODE` command. The next screenshot you see will have red numbered labels on all interactive elements.
    - **Use Command:** `CLICK` with the element's number.
    - **To Exit:** Issue `SWITCH_TO_TEXT_MODE` to return to the default mode.

3.  **GRID Mode (Precision Clicks):** This is for rare cases where you need to click a very specific point on the page that isn't an interactive element, such as a point on a map or an unusual CAPTCHA element.
    - **To Enter:** Issue the `SWITCH_TO_GRID_MODE` command. The next screenshot will have a coordinate grid (A1, B2, etc.).
    - **Use Command:** `GRID_CLICK` with the cell coordinate.
    - **To Exit:** Issue `SWITCH_TO_TEXT_MODE` to return to the default mode.

--- GUIDING PRINCIPLES ---

1.  **MODE STRATEGY:** Start and stay in `TEXT` mode. Only switch to `LABEL` or `GRID` for a single action, then immediately switch back to `TEXT` mode.
2.  **SCROLLING:** ALWAYS scroll down on a page after it loads or after an action to see the full content. The initial view is only the top of the page.
3.  **SEARCH:** Use the `CUSTOM_SEARCH` command to search the web via "Bing". Do NOT use `NAVIGATE` to go to other search engines.
4.  **CREDENTIALS:** If a page requires login, passwords, or personal info, you MUST stop and ask the user for permission with `PAUSE_AND_ASK`.
5.  **OBSTACLES (CAPTCHA):** If you see a CAPTCHA, you can try to solve it using GRID mode. If it's a complex "select all images" type, you cannot solve it. `GO_BACK` and try a different approach.

--- YOUR RESPONSE FORMAT ---

Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

**== PAGE INTERACTION COMMANDS (Primary) ==**

1.  **`TEXT_CLICK`**: (TEXT MODE ONLY) Clicks the first visible element that contains the specified text. This is your main clicking command.
    - **Params:** `{"text": "<text_to_click>"}`
    - **Example:** `{"command": "TEXT_CLICK", "params": {"text": "Customer Reviews"}, "thought": "I need to see the reviews, so I will click the link with that text.", "speak": "Okay, checking the reviews."}`

2.  **`TYPE`**: Types text. You MUST `TEXT_CLICK` or `CLICK` an input field first.
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`

3.  **`SCROLL`**: Scrolls the page up or down.
    - **Params:** `{"direction": "<up|down>"}`

**== MODE SWITCHING & FALLBACK INTERACTION ==**

4.  **`SWITCH_TO_LABEL_MODE`**: Switches to label-based clicking for one action.
    - **Params:** `{}`

5.  **`CLICK`**: (LABEL MODE ONLY) Clicks an element identified by its label number.
    - **Params:** `{"label": <int>}`

6.  **`SWITCH_TO_GRID_MODE`**: Switches to precision grid-based clicking for one action.
    - **Params:** `{}`

7.  **`GRID_CLICK`**: (GRID MODE ONLY) Clicks the center of a specified grid cell.
    - **Params:** `{"cell": "<e.g., 'C5'>"}`

8.  **`SWITCH_TO_TEXT_MODE`**: Switches back to the default text-based interaction.
    - **Params:** `{}`

**== NAVIGATION & BROWSER COMMANDS ==**

9.  **`START_BROWSER`**: Initiates a new browser session. Starts in TEXT mode.
10. **`END_BROWSER`**: Closes the browser when the task is fully complete.
11. **`NAVIGATE`**: Goes directly to a URL.
12. **`CUSTOM_SEARCH`**: Performs a search using "Bing".
13. **`GO_BACK`**: Navigates to the previous page.

**== OTHER COMMANDS ==**

14. **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
15. **`SPEAK`**: For simple conversation.
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
            "is_processing": False, "interaction_mode": "TEXT", # Default mode is now TEXT
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
        session["driver"] = driver
        session["mode"] = "BROWSER"
        session["interaction_mode"] = "TEXT" # Start in TEXT mode
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        traceback.print_exc()
        return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}
    session["tab_handles"] = {}; session["interaction_mode"] = "TEXT"

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
            font = ImageFont.truetype("DejaVuSans.ttf", size=18)
        except IOError:
            font = ImageFont.load_default()

        context_info_text = ""
        mode = session["interaction_mode"]

        if mode == "TEXT":
            print("Capturing state in TEXT mode (no overlays).")
            context_info_text = "Current Mode: TEXT. Use TEXT_CLICK to click on elements by their name."
        
        elif mode == "GRID":
            print("Capturing state in GRID mode.")
            context_info_text = "Current Mode: GRID. Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
            cols = image.width // GRID_CELL_SIZE
            rows = image.height // GRID_CELL_SIZE
            for i in range(rows):
                for j in range(cols):
                    x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                    label = f"{chr(ord('A')+j)}{i+1}"
                    # Draw semi-transparent background box for text
                    draw.rectangle([x1+2, y1+2, x1 + 35, y1 + 22], fill=(0, 0, 0, 128))
                    # Draw the grid label text
                    draw.text((x1 + 4, y1 + 4), label, fill="white", font=font)
                    # Draw the grid lines
                    draw.rectangle([x1, y1, x1 + GRID_CELL_SIZE, y1 + GRID_CELL_SIZE], outline="rgba(255,0,0,100)")

        elif mode == "LABEL":
            print("Capturing state in LABEL mode.")
            elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
            session["labeled_elements"] = {el['label']: el for el in elements}
            context_info_text = "Current Mode: LABEL. Use CLICK with a number.\nInteractive Elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
            for label, el in session["labeled_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                # Draw main red outline
                draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
                # Draw semi-transparent background box for text
                draw.rectangle([x, y-22, x + 25, y], fill=(0, 0, 0, 128))
                # Draw the label number
                draw.text((x + 5, y - 20), str(label), fill="white", font=font)

        image.save(screenshot_path)
        print(f"State captured in {mode} mode.")
        return screenshot_path, context_info_text, tab_info_text
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
    screenshot_path, context_info_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{context_info_text}\n\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "Could not get a view of the page. I will close the browser."); close_browser(session)

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
        send_whatsapp_message(from_number, "I received an invalid response from my AI module. Ending task.")
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
        if not driver:
            send_whatsapp_message(from_number, "I failed to restart the browser. Please start a new task.")
            close_browser(session); return
        time.sleep(1)
        process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        if command == "SWITCH_TO_GRID_MODE":
            session["interaction_mode"] = "GRID"
        elif command == "SWITCH_TO_LABEL_MODE":
            session["interaction_mode"] = "LABEL"
        elif command == "SWITCH_TO_TEXT_MODE":
            session["interaction_mode"] = "TEXT"
        elif command == "GRID_CLICK":
            cell = params.get("cell", "").upper()
            if session["interaction_mode"] != "GRID" or not cell or not cell[0].isalpha() or not cell[1:].isdigit():
                send_whatsapp_message(from_number, f"Invalid GRID_CLICK. Mode is {session['interaction_mode']} or cell format is wrong.")
                action_was_performed = False
            else:
                col_index = ord(cell[0]) - ord('A')
                row_index = int(cell[1:]) - 1
                x = col_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                y = row_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
                print(f"Grid clicking at viewport coordinates ({x}, {y}) for cell {cell}")
                ActionChains(driver).move_by_offset(x, y).click().perform()
                ActionChains(driver).move_by_offset(-x, -y).perform() # Reset offset for next action
        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
            process_next_browser_step(from_number, session, "Browser started. I'm ready for your instructions.")
            return
        elif command == "TEXT_CLICK":
            text_to_click = params.get("text")
            if not text_to_click:
                 send_whatsapp_message(from_number, "TEXT_CLICK failed: No text provided."); action_was_performed = False
            else:
                try:
                    # More robust XPath to find elements by text, value, or aria-label
                    xpath = f"//*[normalize-space(.)='{text_to_click}' or normalize-space(@aria-label)='{text_to_click}' or @value='{text_to_click}']"
                    elements = driver.find_elements(By.XPATH, xpath)
                    
                    # Find the first visible and clickable element
                    element_to_click = None
                    for el in elements:
                        if el.is_displayed() and el.is_enabled():
                            element_to_click = el
                            break
                    
                    if element_to_click:
                        element_to_click.click()
                    else:
                        raise Exception("No visible element found")
                except Exception:
                     # Fallback for partial text match
                    try:
                        xpath_contains = f"//*[contains(normalize-space(.), '{text_to_click}') or contains(normalize-space(@aria-label), '{text_to_click}')]"
                        elements = driver.find_elements(By.XPATH, xpath_contains)
                        element_to_click = next((el for el in elements if el.is_displayed() and el.is_enabled()), None)
                        if element_to_click:
                            element_to_click.click()
                        else:
                            raise Exception("No visible element found with partial match either.")
                    except Exception as e:
                        print(f"TEXT_CLICK failed for '{text_to_click}': {e}")
                        send_whatsapp_message(from_number, f"I couldn't find a clickable element with the text '{text_to_click}'.")
                        action_was_performed = False

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
        elif command == "CLICK":
            label = params.get("label")
            if session["interaction_mode"] != "LABEL" or not session["labeled_elements"].get(label):
                send_whatsapp_message(from_number, f"Invalid CLICK. Mode is {session['interaction_mode']} or label {label} not found.")
                action_was_performed = False
            else:
                try: driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]').click()
                except Exception as e: print(f"Click failed: {e}"); send_whatsapp_message(from_number, "Click failed.")
        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {800 if params.get('direction', 'down') == 'down' else -800});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command == "PAUSE_AND_ASK": return
        elif command == "SPEAK": return
        else: print(f"Unknown command: {command}"); send_whatsapp_message(from_number, f"Unknown command '{command}'."); action_was_performed = True
        
        if action_was_performed: time.sleep(2); process_next_browser_step(from_number, session, f"Action done: {command}")
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
                    session["is_processing"] = False # Allow new user input
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
                    ai_response = call_ai(session["chat_history"], context_text=f"The user's initial request is: '{user_message_text}'. Start by thinking about the first step and issue the appropriate command, like START_BROWSER or CUSTOM_SEARCH.")
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
