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
GRID_CELL_SIZE = 80 # Increased size for a less dense grid
LABEL_FONT_SIZE = 16 # Increased font size for clarity

# --- JAVASCRIPT SNIPPETS ---
JS_GET_ELEMENTS_FOR_MODES = """
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

            // Assign a unique ID for this run, used for clicking later
            const elementId = `magic-agent-element-${labelCounter}`;
            elem.setAttribute('data-magic-agent-id', elementId);

            let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || elem.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').substring(0, 80);
            interactiveElements.push({
                index: labelCounter, // This is the number shown to the AI in TEXT mode
                id: elementId,       // This is the internal ID for clicking
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
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You receive a state (a screenshot and a list of elements or a grid) and issue a single JSON command.

--- ERROR RECOVERY ---
If a command fails, the page may have changed or the command was invalid. Analyze the new screenshot and error message. Do not repeat the failed command. Assess the situation and issue a new command to recover. For example, if a click failed, the element might be gone; look for an alternative on the new screen.

--- INTERACTION MODES ---
You operate in one of three modes. You must manage switching between them.

1.  **TEXT Mode (Default & Primary):** This is your main mode. You will see a clean screenshot and be given a numbered list of all clickable elements and their text (e.g., `1. button: "Sign In"`, `2. link: "Forgot Password"`). To interact, you MUST use the `CLICK_TEXT` command with the corresponding number from the list. This is the fastest and most reliable method.
    - **Example:** The list says `5. button: "Add to Cart"`. You want to click it. Your command is:
      `{"command": "CLICK_TEXT", "params": {"index": 5}, "thought": "I will click the 'Add to Cart' button, which is number 5 in the list.", "speak": "Adding to cart."}`

2.  **LABEL Mode (Fallback for Labeled Elements):** If you need to click an element that is difficult to describe with text (like a text input field you want to clear), switch to this mode using `SWITCH_TO_LABEL_MODE`. The next screenshot will have clear, high-contrast numbers on all interactive elements. Use the `CLICK` command with the element's number. After the action, switch back to TEXT mode.

3.  **GRID Mode (Precision Clicks):** If you need to click something with no text and no label (e.g., a specific point on a map, an image in a CAPTCHA), switch to this mode using `SWITCH_TO_GRID_MODE`. The screenshot will be overlaid with a clear coordinate grid (A1, B2, etc.). Use the `GRID_CLICK` command. After the action, switch back to TEXT mode.

--- GUIDING PRINCIPLES ---
1.  **MODE STRATEGY:** Start and stay in TEXT mode. Only switch to LABEL or GRID for specific tasks that TEXT mode can't handle. Always return to TEXT mode (`SWITCH_TO_TEXT_MODE`) after you're done with a LABEL or GRID action.
2.  **SCROLL:** The initial view is only the top of the page. Always scroll down to see the full context after a page loads or after an action.
3.  **SEARCH:** You MUST use the `CUSTOM_SEARCH` command. Do NOT use `NAVIGATE` to go to Google or other search engines.
4.  **CREDENTIALS:** If a page requires a login or personal info, you MUST use `PAUSE_AND_ASK` to get permission from the user.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---
**== MODE SWITCHING ==**
1. `SWITCH_TO_TEXT_MODE`: Switches to the default text-list-based clicking.
2. `SWITCH_TO_LABEL_MODE`: Switches to numbered-label clicking for the next action.
3. `SWITCH_TO_GRID_MODE`: Switches to precision grid-based clicking for the next action.

**== BROWSER CONTROL ==**
4. `START_BROWSER`: Initiates a new session. Starts in TEXT mode.
5. `END_BROWSER`: Closes the browser. Params: `{"reason": "<summary>"}`
6. `NAVIGATE`, `CUSTOM_SEARCH`, `GO_BACK`
7. `NEW_TAB`, `SWITCH_TO_TAB`, `CLOSE_TAB`

**== PAGE INTERACTION ==**
8. `CLICK_TEXT`: (TEXT MODE ONLY) Clicks an element from the numbered list provided.
   - **Params:** `{"index": <int>}`
   - **Example:** `{"command": "CLICK_TEXT", "params": {"index": 3}, "thought": "Item 3 is the 'Continue' button. I will click it.", "speak": "Clicking continue."}`

9. `CLICK`: (LABEL MODE ONLY) Clicks an element identified by its visual label number.
   - **Params:** `{"label": <int>}`

10. `GRID_CLICK`: (GRID MODE ONLY) Clicks the center of a specified grid cell.
    - **Params:** `{"cell": "<e.g., 'C5'>"}`

11. `TYPE`: Types text. You MUST interact with an input field first (e.g., via `CLICK_TEXT` or `CLICK`).
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`

12. `CLEAR`: (LABEL MODE ONLY) Clears text from a labeled input field.
    - **Params:** `{"label": <int>}`

13. `SCROLL`: Scrolls the page. Params: `{"direction": "<up|down>"}`

**== USER INTERACTION ==**
14. `PAUSE_AND_ASK`: Pauses to ask the user a question. Params: `{"question": "<your_question>"}`
15. `SPEAK`: For simple conversation. Params: `{"text": "<your_response>"}`
"""

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data); response.raise_for_status()
        print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text message: {e} - {response.text}")

def send_whatsapp_image(to, image_path, caption=""):
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': (image_path.name, open(image_path, 'rb'), 'image/png'), 'messaging_product': (None, 'whatsapp'), 'type': (None, 'image/png')}
    try:
        response = requests.post(upload_url, headers=headers, files=files); response.raise_for_status()
        media_id = response.json().get('id')
        if not media_id: print("Failed to get media ID."); return
        send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
        requests.post(send_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}, json=data).raise_for_status()
        print(f"Sent image message to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e: print(f"Error sending/uploading WhatsApp image: {e} - {getattr(e.response, 'text', 'No response text')}")

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "page_elements": {}, "tab_handles": {},
            "is_processing": False, "interaction_mode": "TEXT", # Default mode
            "stop_requested": False, "interrupt_requested": False
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options(); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session.update({"driver": driver, "mode": "BROWSER", "interaction_mode": "TEXT"})
        return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"):
        try: session["driver"].quit()
        except Exception: pass
    session.update({"driver": None, "mode": "CHAT", "original_prompt": "", "page_elements": {}, "tab_handles": {}, "interaction_mode": "TEXT"})

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    try:
        # Get Tab Info
        window_handles = driver.window_handles; current_handle = driver.current_window_handle
        session["tab_handles"] = {i + 1: handle for i, handle in enumerate(window_handles)}
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {i+1}: {driver.title if handle == current_handle else '(Other Tab)'} {'(Current)' if handle == current_handle else ''}\n" for i, handle in session["tab_handles"].items()])
    except Exception as e: print(f"Could not get tab info: {e}"); tab_info_text = "Could not get tab info."

    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        try:
            main_font = ImageFont.truetype("DejaVuSans.ttf", size=LABEL_FONT_SIZE)
        except IOError:
            main_font = ImageFont.load_default()

        mode_specific_text = ""
        mode = session["interaction_mode"]

        # Regardless of mode, we get all elements first
        elements = driver.execute_script(JS_GET_ELEMENTS_FOR_MODES)
        session["page_elements"] = {el['index']: el for el in elements}

        if mode == "TEXT":
            print("Capturing state in TEXT mode.")
            # Create the numbered list for the AI
            text_list = [f"{el['index']}. {el['tag']}: \"{el['text']}\"" for el in elements]
            mode_specific_text = "Clickable Elements List:\n" + "\n".join(text_list)
            # No drawing on the image in TEXT mode

        elif mode == "GRID":
            print("Capturing state in GRID mode.")
            mode_specific_text = "GRID MODE: Use GRID_CLICK with a cell coordinate (e.g., 'C5')."
            cols, rows = image.width // GRID_CELL_SIZE, image.height // GRID_CELL_SIZE
            for i in range(rows):
                for j in range(cols):
                    x1, y1 = j * GRID_CELL_SIZE, i * GRID_CELL_SIZE
                    label = f"{chr(ord('A')+j)}{i+1}"
                    bbox = draw.textbbox((x1 + 3, y1 + 3), label, font=main_font)
                    draw.rectangle((bbox[0]-2, bbox[1]-2, bbox[2]+2, bbox[3]+2), fill="red")
                    draw.text((x1 + 3, y1 + 3), label, fill="white", font=main_font)

        elif mode == "LABEL":
            print("Capturing state in LABEL mode.")
            mode_specific_text = "LABEL MODE: Use CLICK with a label number."
            for index, el in session["page_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                draw.rectangle([x, y, x + w, y + h], outline="red", width=3)
                label_text = str(index)
                text_x, text_y = x, y - (LABEL_FONT_SIZE + 6) if y > (LABEL_FONT_SIZE + 6) else y + h
                bbox = draw.textbbox((text_x, text_y), label_text, font=main_font)
                draw.rectangle((bbox[0]-4, bbox[1]-2, bbox[2]+4, bbox[3]+2), fill="red")
                draw.text((text_x, text_y), label_text, fill="white", font=main_font)

        image.save(screenshot_path)
        print(f"State captured in {mode} mode.")
        # Combine tab info with mode-specific text
        full_context_text = f"{tab_info_text}\n{mode_specific_text}"
        return screenshot_path, full_context_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, ""

def call_ai(chat_history, context_text, image_path):
    prompt_parts = [context_text, {"mime_type": "image/png", "data": image_path.read_bytes()}]
    last_error = "No API keys were available or all failed."
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            response = model.generate_content(prompt_parts, generation_config={"temperature": 0.0}) # Low temp for deterministic actions
            print("AI call successful."); return response.text
        except Exception as e:
            print(f"API key #{i+1} failed. Error: {e}"); last_error = e
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Error connecting to my brain."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, context_text = get_page_state(session["driver"], session)
    if screenshot_path:
        # Prepend user goal and the last action's status to the context
        full_context = f"User's Goal: {session['original_prompt']}\nStatus: {caption}\n\n{context_text}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], full_context, screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "Could not get a view of the page. Ending task.")
        close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    if session.get("stop_requested"): print("Stop was requested."); session.update({"stop_requested": False, "chat_history": []}); return
    if session.get("interrupt_requested"): print("Interrupt was requested."); session["interrupt_requested"] = False; return

    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, f"AI gave a non-JSON response: {ai_response_text}"); close_browser(session); return

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought} | Mode: {session['interaction_mode']}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)

    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER"]:
        send_whatsapp_message(from_number, "Browser isn't running. Restarting it to continue...")
        if not start_browser(session): send_whatsapp_message(from_number, "Failed to restart browser."); close_browser(session); return
        time.sleep(1); process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        next_caption = f"Action: '{command}' success. {speak}"
        
        # Mode Switching
        if command.startswith("SWITCH_TO_"):
            session["interaction_mode"] = command.replace("SWITCH_TO_", "").replace("_MODE", "")
        
        # Page Interaction
        elif command == "CLICK_TEXT":
            if session["interaction_mode"] != "TEXT":
                raise ValueError("Cannot use CLICK_TEXT outside of TEXT mode.")
            index = params.get("index")
            element_id = session["page_elements"].get(index, {}).get('id')
            if not element_id: raise ValueError(f"Invalid index {index} provided.")
            driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-id="{element_id}"]').click()
        
        elif command == "CLICK":
            if session["interaction_mode"] != "LABEL":
                raise ValueError("Cannot use CLICK outside of LABEL mode.")
            label = params.get("label")
            element_id = session["page_elements"].get(label, {}).get('id')
            if not element_id: raise ValueError(f"Invalid label {label} provided.")
            driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-id="{element_id}"]').click()
        
        elif command == "GRID_CLICK":
            if session["interaction_mode"] != "GRID":
                raise ValueError("Cannot use GRID_CLICK outside of GRID mode.")
            cell = params.get("cell", "").upper()
            if not cell or not cell[0].isalpha() or not cell[1:].isdigit(): raise ValueError(f"Invalid cell format: {cell}.")
            col_index, row_index = ord(cell[0]) - ord('A'), int(cell[1:]) - 1
            x, y = col_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2), row_index * GRID_CELL_SIZE + (GRID_CELL_SIZE / 2)
            print(f"Grid clicking at ({x}, {y}) for cell {cell}")
            driver.execute_script(f"document.elementFromPoint({x}, {y}).click();")

        elif command == "TYPE":
            ActionChains(driver).send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()

        elif command == "CLEAR":
            if session["interaction_mode"] != "LABEL":
                raise ValueError("Cannot use CLEAR outside of LABEL mode.")
            label = params.get("label")
            element_id = session["page_elements"].get(label, {}).get('id')
            if not element_id: raise ValueError(f"Invalid label {label} for CLEAR.")
            element_to_clear = driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-id="{element_id}"]')
            element_to_clear.send_keys(Keys.CONTROL + "a"); element_to_clear.send_keys(Keys.DELETE)

        elif command == "SCROLL":
            direction = 1 if params.get('direction', 'down') == 'down' else -1
            driver.execute_script(f"window.scrollBy(0, window.innerHeight * 0.8 * {direction});")

        # Browser Control
        elif command == "START_BROWSER":
            if not start_browser(session): raise Exception("Failed to start browser.")
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "NEW_TAB": driver.switch_to.new_window('tab'); driver.get(params["url"]) if "url" in params else None
        elif command == "CLOSE_TAB":
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
            else: action_was_performed = False; next_caption = "Cannot close the last tab."
        elif command == "SWITCH_TO_TAB":
            handle = session["tab_handles"].get(params.get("tab_id"))
            if handle: driver.switch_to.window(handle)
            else: action_was_performed = False; next_caption = f"Could not find tab ID {params.get('tab_id')}."
        
        # End/Pause
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Task Summary:*\n{params.get('reason', 'Task completed.')}"); close_browser(session); return
        elif command in ["PAUSE_AND_ASK", "SPEAK"]: return # No further action needed
        else: action_was_performed = False; next_caption = f"Unknown command: '{command}'."
        
        if action_was_performed:
            time.sleep(2) # Wait for page to react
            process_next_browser_step(from_number, session, next_caption)
        else:
            send_whatsapp_message(from_number, f"Action failed: {next_caption}")

    except Exception as e:
        error_summary = f"Error on '{command}': {str(e).splitlines()[0]}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, f"An action failed. Recovering...")
        time.sleep(1)
        process_next_browser_step(from_number, session, caption=f"ERROR: {error_summary}. Please analyze the screen and proceed differently.")


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)
    
    body = request.get_json()
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        if "messages" not in entry: return Response(status=200) # Not a message
        
        message_info = entry["messages"][0]
        message_id = message_info.get("id")
        if message_id in processed_message_ids:
            print(f"Duplicate message ID {message_id}. Ignoring."); return Response(status=200)
        processed_message_ids.add(message_id)
        
        if message_info.get("type") != "text":
            send_whatsapp_message(message_info.get("from"), "I only process text messages."); return Response(status=200)

        from_number, user_message_text = message_info["from"], message_info["text"]["body"]
        print(f"Received from {from_number}: '{user_message_text}'")
        session = get_or_create_session(from_number)
        
        command_text = user_message_text.strip().lower()
        if command_text == "/stop":
            session["stop_requested"] = True; close_browser(session); session["is_processing"] = False
            send_whatsapp_message(from_number, "Request stopped. Task cancelled."); return Response(status=200)
        if command_text == "/interrupt":
            if session["mode"] != "BROWSER": send_whatsapp_message(from_number, "No browser task to interrupt.")
            else: session["interrupt_requested"] = True; session["is_processing"] = False; send_whatsapp_message(from_number, "Interrupted. What's next?")
            return Response(status=200)
        if command_text == "/clear":
            close_browser(session); del user_sessions[from_number]
            send_whatsapp_message(from_number, "Your session and chat history are cleared."); return Response(status=200)

        if session.get("is_processing"):
            send_whatsapp_message(from_number, "Please wait, I'm working. Use /interrupt or /stop."); return Response(status=200)
        
        session["is_processing"] = True
        try:
            session["chat_history"].append({"role": "user", "parts": [user_message_text]})
            if session["mode"] == "CHAT":
                session["original_prompt"] = user_message_text
                # Use a simpler initial prompt to decide if browsing is needed
                initial_prompt = f"User wants to: '{user_message_text}'. Your first command should be START_BROWSER if this requires a browser, or SPEAK/PAUSE_AND_ASK if it's a simple chat question."
                ai_response = call_ai([], initial_prompt, None) # No history/image for initial decision
                process_ai_command(from_number, ai_response)
            elif session["mode"] == "BROWSER":
                process_next_browser_step(from_number, session, f"New instructions from user: {user_message_text}")
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
