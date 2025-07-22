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

# --- NEW, MORE DETAILED SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," an AI expert at controlling a web browser to complete tasks for a user.
You operate by receiving a state (a screenshot and tab info) and issuing a single command in JSON format.

**IMPORTANT: If you need any information from the user during the process (like a password, a decision, or clarification), you MUST use the `PAUSE_AND_ASK` command. Do not guess or make things up. After you ask, the user's next message will be their answer, and you can then resume the task.**

**CORE WORKFLOW:**
1.  **Analyze User Request:** Understand the user's ultimate goal.
2.  **Choose Command:** Select ONE command from the list below that makes progress towards the goal.
3.  **Provide Rationale:** In the "thought" field, explain WHY you chose this command.
4.  **Inform User:** In the "speak" field, write a brief, friendly message for the user about what you're doing.

**CONTEXT PROVIDED TO YOU ON EACH TURN (IN BROWSER MODE):**
- **Screenshot:** A PNG image of the current tab. Interactive elements are marked with red numbered boxes.
- **Element List:** A text list of the numbered elements, their type (e.g., 'button', 'input'), and their visible text.
- **Tab List:** A text list of all open tabs, their titles, and which one is currently active.

**Your responses MUST ALWAYS be a single JSON object.**

--- COMMAND REFERENCE ---

**== BROWSER START/STOP COMMANDS ==**

1.  **`START_BROWSER`**:
    - **Description:** Initiates a new browser session.
    - **Params:** `{}`

2.  **`END_BROWSER`**:
    - **Description:** Closes the entire browser session when the task is fully complete.
    - **Params:** `{"reason": "<summary of findings or completion message>"}`

**== NAVIGATION COMMANDS ==**

3.  **`NAVIGATE`**:
    - **Description:** Goes directly to a specific URL.
    - **Params:** `{"url": "<full_url>"}`

4.  **`CUSTOM_SEARCH`**:
    - **Description:** Performs a search using the dedicated custom search engine.
    - **Params:** `{"query": "<search_term>"}`
    - **Example:** `{"command": "CUSTOM_SEARCH", "params": {"query": "latest AI news"}, "thought": "The user wants to find news, so I will use the custom search engine.", "speak": "Searching for 'latest AI news'..."}`

**== PAGE INTERACTION COMMANDS ==**

5.  **`CLICK`**:
    - **Description:** Clicks an element on the page, identified by its label number.
    - **Params:** `{"label": <int>}`

6.  **`TYPE`**:
    - **Description:** Types text where the cursor is currently located. **IMPORTANT: You MUST use the `CLICK` command on a text field *before* using `TYPE`.**
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}`

7.  **`CLEAR`**:
    - **Description:** Clears all text from an input field.
    - **Params:** `{"label": <int>}`

8.  **`SCROLL`**:
    - **Description:** Scrolls the current page up or down.
    - **Params:** `{"direction": "<up|down>"}`

**== TAB MANAGEMENT COMMANDS ==**

9.  **`NEW_TAB`**:
    - **Description:** Opens a new browser tab.
    - **Params:** `{"url": "<optional_url_to_open>"}`

10. **`SWITCH_TO_TAB`**:
    - **Description:** Switches focus to a different open tab using its `tab_id`.
    - **Params:** `{"tab_id": <int>}`

11. **`CLOSE_TAB`**:
    - **Description:** Closes the currently active tab.
    - **Params:** `{}`

**== USER INTERACTION COMMANDS ==**

12. **`PAUSE_AND_ASK`**:
    - **Description:** Pauses the task to ask the user a question when you are blocked or need information.
    - **Params:** `{"question": "<your_question_for_the_user>"}`

13. **`SPEAK`**:
    - **Description:** For use in CHAT mode (when browser is not open) for simple conversation.
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
    """Retrieves or initializes a new session for a given phone number."""
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "labeled_elements": {}, "tab_handles": {},
            "is_processing": False
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver
        session["mode"] = "BROWSER"
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}; session["tab_handles"] = {}

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
    except Exception as e:
        print(f"Could not get tab info: {e}"); return None, "", ""
    try:
        elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
        session["labeled_elements"] = {el['label']: el for el in elements}
        labels_text = "Interactive Elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
        png_data = driver.get_screenshot_as_png(); image = Image.open(io.BytesIO(png_data)); draw = ImageDraw.Draw(image)
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=14)
        except IOError: font = ImageFont.load_default()
        for label, el in session["labeled_elements"].items():
            x, y, w, h = el['x'], el['y'], el['width'], el['height']
            draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
            draw.text((x, y - 15 if y > 15 else y), str(label), fill="red", font=font)
        image.save(screenshot_path); print(f"State captured: {len(elements)} labels, {len(tabs)} tabs.")
        return screenshot_path, labels_text, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc(); return None, "", tab_info_text

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
            print("AI call successful.")
            return response.text
        except Exception as e: print(f"API key #{i+1} failed. Error: {e}"); last_error = e; continue
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Error connecting to my brain."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, labels_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{labels_text}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "Could not get a view of the page. Closing browser.")
        close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
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
    if command == "START_BROWSER":
        driver = start_browser(session)
        if not driver: send_whatsapp_message(from_number, "Could not open browser."); close_browser(session); return
        time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE); time.sleep(1) # <-- UPDATED
        process_next_browser_step(from_number, session, "Browser started. What's next?")
        return
    if not driver and command not in ["SPEAK", "START_BROWSER"]:
        send_whatsapp_message(from_number, "Browser isn't running. Please start a task first."); return
    try:
        action_was_performed = True
        if command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE)) # <-- UPDATED
        elif command == "CUSTOM_SEARCH": # <-- UPDATED
            query = quote_plus(params.get('query', ''))
            search_url = CUSTOM_SEARCH_URL_TEMPLATE % query
            driver.get(search_url)
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
            if not session["labeled_elements"].get(label):
                send_whatsapp_message(from_number, f"Label {label} is not a valid choice."); action_was_performed = False
            else:
                try: driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]').click()
                except Exception as e: print(f"Click failed: {e}"); send_whatsapp_message(from_number, "I tried to click that, but something went wrong.")
        elif command == "TYPE":
            action = ActionChains(driver); action.send_keys(params.get("text", "")).perform()
            if params.get("enter"): ActionChains(driver).send_keys(Keys.ENTER).perform()
        elif command == "CLEAR":
            label = params.get("label")
            if not session["labeled_elements"].get(label):
                send_whatsapp_message(from_number, f"Label {label} is not valid for clearing."); action_was_performed = False
            else:
                try:
                    element_to_clear = driver.find_element(By.CSS_SELECTOR, f'[data-magic-agent-label="{label}"]')
                    element_to_clear.send_keys(Keys.CONTROL + "a"); element_to_clear.send_keys(Keys.DELETE)
                except Exception as e: print(f"Clear failed: {e}"); send_whatsapp_message(from_number, "I tried to clear that field, but something went wrong.")
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {600 if params.get('direction', 'down') == 'down' else -600});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command == "PAUSE_AND_ASK": return
        elif command == "SPEAK": return
        else: print(f"Unknown command: {command}"); send_whatsapp_message(from_number, f"Unknown command '{command}'."); action_was_performed = True
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
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            message_id = message_info.get("id")

            if message_id in processed_message_ids:
                print(f"Duplicate message ID {message_id} received. Ignoring.")
                return Response(status=200)
            processed_message_ids.add(message_id)
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I only process text messages.")
                return Response(status=200)

            from_number = message_info["from"]
            user_message_text = message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            if session.get("is_processing"):
                send_whatsapp_message(from_number, "Please wait, I'm still working on your previous request.")
                return Response(status=200)
            
            try:
                session["is_processing"] = True
                session["chat_history"].append({"role": "user", "parts": [user_message_text]})

                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=user_message_text)
                    process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    if not session.get("driver"):
                        close_browser(session)
                        ai_response = call_ai(session["chat_history"], context_text=user_message_text)
                        process_ai_command(from_number, ai_response)
                        return Response(status=200)
                    send_whatsapp_message(from_number, "Okay, using that info to continue...")
                    process_next_browser_step(from_number, session, "Continuing with new instructions.")
            finally:
                session["is_processing"] = False

        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
