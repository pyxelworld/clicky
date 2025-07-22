import os
import json
import requests
import time
import io
import traceback
import shutil # <-- IMPORTED FOR /clear COMMAND
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
AI_MODEL_NAME = "gemini-2.0-flash"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- CONSTANTS ---
CUSTOM_SEARCH_URL_BASE = "https://cse.google.com/cse?cx=b0ccd7d88551d4e50"
CUSTOM_SEARCH_URL_TEMPLATE = "https://cse.google.com/cse?cx=b0ccd7d88551d4e50#gsc.tab=0&gsc.sort=&gsc.q=%s"
GRID_SIZE = 100 # Size of grid cells in pixels

# --- JAVASCRIPT FOR ELEMENT LABELING ---
JS_GET_INTERACTIVE_ELEMENTS = """
    const elements = Array.from(document.querySelectorAll('a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'));
    const interactiveElements = []; let labelCounter = 1;
    for (const elem of elements) {
        const rect = elem.getBoundingClientRect();
        if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0 && rect.bottom <= window.innerHeight && rect.right <= window.innerWidth) {
            elem.setAttribute('data-magic-agent-label', labelCounter);
            let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || elem.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').substring(0, 50);
            interactiveElements.push({label: labelCounter, x: rect.left, y: rect.top, width: rect.width, height: rect.height, tag: elem.tagName.toLowerCase(), text: text});
            labelCounter++;
        }
    } return interactiveElements;
"""

# --- NEW, MORE DETAILED SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser to complete tasks for a user. You operate by receiving a state (screenshot, context) and issuing a single command in JSON format.

--- GUIDING PRINCIPLES ---

1.  **LOGIN & CREDENTIALS**: If you encounter a page that requires a login, a password, or any personal information, you MUST stop and ask the user for it. Use the `PAUSE_AND_ASK` command. DO NOT try to guess or proceed without user input.

2.  **PROACTIVE EXPLORATION & SCROLLING**: ALWAYS scroll down on a page after it loads. The initial view is only the top. You must scroll to understand the full context. Assume important content is "below the fold."

3.  **SEARCH STRATEGY ("Clicky Search")**: To search the web, you MUST use the `CUSTOM_SEARCH` command. Be a smart searcher: use operators like `"exact phrase"`, `OR`, and `site:example.com` to get better results.

4.  **HANDLING OBSTACLES (CAPTCHA)**: If you see a CAPTCHA ("I'm not a robot", "reCAPTCHA"), you cannot solve it in element mode. Your strategy is to be self-sufficient:
    - Option A: Use `GO_BACK` to return to the search results and choose a different link.
    - Option B (Advanced): Switch to grid mode with `SWITCH_TO_GRID_MODE`, then try to click the checkbox with `GRID_CLICK`. If it works, switch back with `SWITCH_TO_ELEMENT_MODE`. If it fails, use `GO_BACK`.

5.  **SHOPPING STRATEGY**: When a user wants to shop, ask for specifics: what exact product are they looking for? What is their price range? Once on a shopping site, use features like 'Sort by Price' or category filters to narrow down the results effectively.

6.  **GRID MODE FOR PRECISION**: Most of the time, you will be in 'Element Mode'. However, if you need to click something that is not a standard, labeled element (like a tricky dropdown menu option, a specific point on a map, or a CAPTCHA checkbox), you MUST switch to grid mode.
    - First, issue the `SWITCH_TO_GRID_MODE` command.
    - You will then receive a screenshot with a grid overlay.
    - Issue a `GRID_CLICK` command with the cell coordinate (e.g., "D5") that covers the target.
    - Once the click is done, you MUST issue the `SWITCH_TO_ELEMENT_MODE` command to return to normal operation.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

*   **`START_BROWSER`**: Initiates a new browser session.
*   **`END_BROWSER`**: Closes the browser when the task is fully complete. `{"reason": "<summary>"}`
*   **`NAVIGATE`**: Goes directly to a URL. `{"url": "<full_url>"}`
*   **`CUSTOM_SEARCH`**: Searches the web. `{"query": "<search_term>"}`
*   **`GO_BACK`**: Navigates to the previous page.
*   **`CLICK`**: Clicks a labeled element. `{"label": <int>}`
*   **`TYPE`**: Types text where the cursor is. `{"text": "<text>", "enter": <bool>}`
*   **`CLEAR`**: Clears text from an input field. `{"label": <int>}`
*   **`SCROLL`**: Scrolls the page. `{"direction": "<up|down>"}`
*   **`SWITCH_TO_GRID_MODE`**: Changes the view to a clickable grid for precision tasks.
*   **`GRID_CLICK`**: Clicks a cell in grid mode. `{"cell": "<e.g., C5>"}`
*   **`SWITCH_TO_ELEMENT_MODE`**: Switches back to the default element-labeling mode.
*   **`NEW_TAB`**, **`SWITCH_TO_TAB`**, **`CLOSE_TAB`**: Standard tab management.
*   **`PAUSE_AND_ASK`**: Asks the user a question when you are blocked. `{"question": "<your_question>"}`
*   **`SPEAK`**: For CHAT mode conversation. `{"text": "<response>"}`
"""

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Sent text to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text: {e} - {response.text}")

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
        print(f"Sent image to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp image: {e} - {response.text}")

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {"mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "", "user_dir": user_dir,
                   "labeled_elements": {}, "tab_handles": {}, "is_processing": False, "interaction_mode": "ELEMENT"}
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--headless=new"); options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage"); options.add_argument("--window-size=1280,800")
    options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options); session["driver"] = driver; session["mode"] = "BROWSER"; return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}");
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}; session["tab_handles"] = {}

def _get_excel_col(n):
    string = ""; n += 1
    while n > 0: n, remainder = divmod(n - 1, 26); string = chr(65 + remainder) + string
    return string

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
    
    png_data = driver.get_screenshot_as_png(); image = Image.open(io.BytesIO(png_data)); draw = ImageDraw.Draw(image)
    try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=12)
    except IOError: font = ImageFont.load_default()
    
    interaction_mode = session.get("interaction_mode", "ELEMENT")
    labels_text = ""

    if interaction_mode == "ELEMENT":
        try:
            elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
            session["labeled_elements"] = {el['label']: el for el in elements}
            labels_text = "Interactive Elements (Element Mode):\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
            for label, el in session["labeled_elements"].items():
                x, y, w, h = el['x'], el['y'], el['width'], el['height']
                draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
                draw.text((x + 2, y - 14 if y > 14 else y + 2), str(label), fill="red", font=font)
        except Exception as e: print(f"Error getting element state: {e}"); traceback.print_exc()
    
    elif interaction_mode == "GRID":
        labels_text = "Grid Mode is Active. Use `GRID_CLICK` with cell coordinates (e.g., 'C5')."
        cols = image.width // GRID_SIZE; rows = image.height // GRID_SIZE
        for i in range(cols + 1): draw.line([(i * GRID_SIZE, 0), (i * GRID_SIZE, image.height)], fill=(0, 255, 0, 128), width=1)
        for i in range(rows + 1): draw.line([(0, i * GRID_SIZE), (image.width, i * GRID_SIZE)], fill=(0, 255, 0, 128), width=1)
        for r in range(rows):
            for c in range(cols):
                col_name = _get_excel_col(c); cell_name = f"{col_name}{r + 1}"
                draw.text((c * GRID_SIZE + 3, r * GRID_SIZE + 3), cell_name, fill=(0, 255, 0), font=font)

    image.save(screenshot_path); print(f"State captured in {interaction_mode} mode.")
    return screenshot_path, labels_text, tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: {e}"}, "thought": "Image read failed.", "speak": "Error with screen view."})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting API call with key #{i+1}..."); genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(prompt_parts); print("AI call successful."); return response.text
        except Exception as e: print(f"API key #{i+1} failed: {e}"); last_error = e; continue
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Error connecting to my brain."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, labels_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{labels_text}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "Could not get a view of the page. Closing browser."); close_browser(session)

def _get_grid_coordinates(cell_str):
    if not cell_str or not cell_str[0].isalpha() or not cell_str[1:].isdigit(): return None
    col_str = "".join(filter(str.isalpha, cell_str)); row_str = "".join(filter(str.isdigit, cell_str))
    col_index = 0; for char in col_str.upper(): col_index = col_index * 26 + (ord(char) - 65) + 1
    col_index -= 1; row_index = int(row_str) - 1
    x = (col_index * GRID_SIZE) + (GRID_SIZE / 2); y = (row_index * GRID_SIZE) + (GRID_SIZE / 2)
    return x, y

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        if session["mode"] == "BROWSER": close_browser(session)
        return
        
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Mode: {session.get('interaction_mode')} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)
    
    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER"]:
        send_whatsapp_message(from_number, "Browser was closed. Restarting to continue your task..."); driver = start_browser(session)
        if not driver: send_whatsapp_message(from_number, "Failed to restart browser."); close_browser(session); return
        time.sleep(1); process_ai_command(from_number, ai_response_text); return

    try:
        action_was_performed = True
        if command == "START_BROWSER":
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
            time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1)
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "SWITCH_TO_GRID_MODE": session["interaction_mode"] = "GRID"
        elif command == "SWITCH_TO_ELEMENT_MODE": session["interaction_mode"] = "ELEMENT"
        elif command == "GRID_CLICK":
            coords = _get_grid_coordinates(params.get("cell", ""))
            if not coords: send_whatsapp_message(from_number, f"Invalid cell format: {params.get('cell')}."); action_was_performed = False
            else:
                x, y = coords; body = driver.find_element(By.TAG_NAME, 'body')
                ActionChains(driver).move_to_element_with_offset(body, 0, 0).move_by_offset(x, y).click().perform()
        elif command == "CLICK":
            if session.get("interaction_mode") != "ELEMENT": send_whatsapp_message(from_number, "Cannot use CLICK in Grid Mode. Use GRID_CLICK or switch modes."); action_was_performed = False
            else:
                label = params.get("label");
                if not session["labeled_elements"].get(label): send_whatsapp_message(from_number, f"Label {label} is not a valid choice."); action_was_performed = False
                else:
                    try: driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]').click()
                    except Exception as e: print(f"Click failed: {e}"); send_whatsapp_message(from_number, "I tried to click that, but something went wrong.")
        elif command == "TYPE": action = ActionChains(driver); action.send_keys(params.get("text", "")).perform(); action.send_keys(Keys.ENTER).perform() if params.get("enter") else None
        elif command == "CLEAR":
            label = params.get("label")
            if not session["labeled_elements"].get(label): send_whatsapp_message(from_number, f"Label {label} is not valid for clearing."); action_was_performed = False
            else:
                try: element = driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]'); element.send_keys(Keys.CONTROL + "a"); element.send_keys(Keys.DELETE)
                except Exception as e: print(f"Clear failed: {e}"); send_whatsapp_message(from_number, "I tried to clear that field, but something went wrong.")
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {600 if params.get('direction', 'down') == 'down' else -600});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command == "PAUSE_AND_ASK": return
        elif command == "SPEAK": return
        else: # All other standard browser commands
            if command == "NEW_TAB": driver.switch_to.new_window('tab'); driver.get(params["url"]) if "url" in params and params["url"] else None
            elif command == "CLOSE_TAB":
                if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
                else: send_whatsapp_message(from_number, "I can't close the last tab."); action_was_performed = False
            elif command == "SWITCH_TO_TAB":
                handle = session["tab_handles"].get(params.get("tab_id"))
                if handle: driver.switch_to.window(handle)
                else: send_whatsapp_message(from_number, f"I couldn't find tab ID {params.get('tab_id')}."); action_was_performed = False
            else: print(f"Unknown command: {command}"); send_whatsapp_message(from_number, f"Unknown command '{command}'.")
        
        if action_was_performed: time.sleep(2); process_next_browser_step(from_number, session, f"Action done: {speak}")
    except Exception as e: print(f"Error during browser action: {e}"); traceback.print_exc(); send_whatsapp_message(from_number, "An action failed. Closing browser."); close_browser(session)

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)
    
    if request.method == 'POST':
        body = request.get_json()
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]; message_id = message_info.get("id")
            if message_id in processed_message_ids: print(f"Duplicate message ID {message_id} received. Ignoring."); return Response(status=200)
            processed_message_ids.add(message_id)
            if message_info.get("type") != "text": send_whatsapp_message(message_info.get("from"), "I only process text messages."); return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            # --- HANDLE USER COMMANDS ---
            if user_message_text.strip().lower() == '/stop':
                close_browser(session); send_whatsapp_message(from_number, "Your session has been stopped and the browser is closed."); return Response(status=200)
            if user_message_text.strip().lower() == '/clear':
                close_browser(session)
                try: shutil.rmtree(session['user_dir'])
                except FileNotFoundError: pass
                if from_number in user_sessions: del user_sessions[from_number]
                send_whatsapp_message(from_number, "Your session and all data have been cleared. We're starting fresh!"); return Response(status=200)

            if session.get("is_processing"): send_whatsapp_message(from_number, "Please wait, I'm still working on your previous request."); return Response(status=200)
            
            try:
                session["is_processing"] = True; session["chat_history"].append({"role": "user", "parts": [user_message_text]})
                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=user_message_text); process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    send_whatsapp_message(from_number, "Okay, using that info to continue...")
                    process_next_browser_step(from_number, session, "Continuing with new instructions.")
            finally: session["is_processing"] = False
        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---"); app.name = 'whatsapp'; app.run(port=5000, debug=False)
