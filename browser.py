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
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# --- CONFIGURATION (WITH API KEY ROTATION) ---
GEMINI_API_KEYS = [
    "AIzaSyCnnkNB4qPXE9bgTwRH_Jj5lxUOq_xivJo", "AIzaSyDuAT3AP1wNd-FNb0QmvwQcSTD2dM3ZStc",
    "AIzaSyCuKxOa7GoY6id_aG-C3_uhvfJ1iI0SeQ0", "AIzaSyBwASUXeAVJ6xFFZdfjNZO5Hsumr4KAntw",
    "AIzaSyB4EZanzOFSu589lfBVO3M8dy72fBW2ObY", "AIzaSyASbyRix7Cbae7qCgPQntshA5DVJSVJbo4",
    "AIzaSyD07UM2S3qdSUyyY0Hp4YtN04J60PcO41w", "AIzaSyA9037TcPXJ2tdSrEe-hzLCn0Xa5zjiUOo",
    "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
]
current_api_key_index = 0

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
BROWSER_COMMANDS = {"NAVIGATE", "BRAVE_SEARCH", "CLICK", "TYPE", "SCROLL", "NEW_TAB", "SWITCH_TO_TAB", "CLOSE_TAB"}

# --- JAVASCRIPT FOR ELEMENT LABELING ---
JS_GET_INTERACTIVE_ELEMENTS = """
    const elements = Array.from(document.querySelectorAll('a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'));
    const interactiveElements = []; let labelCounter = 1;
    for (let i = 0; i < elements.length; i++) {
        const elem = elements[i], rect = elem.getBoundingClientRect();
        if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0 && rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && rect.right <= (window.innerWidth || document.documentElement.clientWidth)) {
            let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || elem.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').substring(0, 50);
            interactiveElements.push({label: labelCounter, x: rect.left, y: rect.top, width: rect.width, height: rect.height, tag: elem.tagName.toLowerCase(), text: text});
            labelCounter++;
        }
    } return interactiveElements;
"""

# --- ENHANCED SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," an AI expert controlling a web browser. Your #1 priority is to be cautious and precise.

**GUIDING PRINCIPLES:**
1.  **ACT FIRST, ASK LATER:** Do not ask the user for guidance before you have at least tried to `NAVIGATE` or `BRAVE_SEARCH`. You must see the first page before deciding if you need help.
2.  **WHEN IN DOUBT, PAUSE:** After seeing a page, if it is unexpected (e.g., a CAPTCHA, a login wall, an error) or you are unsure how to proceed, your default action is `PAUSE_AND_ASK`. Formulate a clear, conversational question to the user in the 'speak' field.
3.  **NAVIGATE DIRECTLY:** If you know the exact URL (e.g., wikipedia.org), use the `NAVIGATE` command. It is faster and more reliable than searching.
4.  **BE THOROUGH:** If information isn't immediately visible, your default action is to `SCROLL` to explore the rest of the page.

**CONTEXT PROVIDED TO YOU:** A screenshot with interactive elements marked with red numbered boxes, a list of those elements, and a list of open tabs.
**YOUR RESPONSE:** You must always respond with a single JSON object.

--- COMMAND REFERENCE ---
**== NAVIGATION & SEARCH (Implicitly starts browser) ==**
1. `NAVIGATE`: Goes directly to a URL. Params: `{"url": "<full_url>"}`
2. `BRAVE_SEARCH`: Performs a Brave Search. Params: `{"query": "<search_term>"}`
**== PAGE INTERACTION ==**
3. `CLICK`: Clicks an element by its label number. Params: `{"label": <int>}`
4. `TYPE`: Types text into an input field (automatically clicks it first). Params: `{"label": <int>, "text": "<text_to_type>", "enter": <true/false>}`
5. `SCROLL`: Scrolls the page up or down. Params: `{"direction": "<up|down>"}`
**== TAB MANAGEMENT ==**
6. `NEW_TAB`: Opens a new tab. Params: `{"url": "<optional_url>"}`
7. `SWITCH_TO_TAB`: Switches focus to an open tab by its `tab_id`. Params: `{"tab_id": <int>}`
8. `CLOSE_TAB`: Closes the current tab. Params: `{}`
**== SESSION & CHAT ==**
9. `PAUSE_AND_ASK`: Pauses the browser to ask the user a conversational question. **Use this if you are uncertain about the page content.**
   - The user's response will allow you to re-evaluate the same screen with new instructions.
   - Params: `{"speak": "<Your full, natural question to the user. e.g., 'Hmm, this page requires a login. Should I look for a sign-up button instead?' >"}`
10. `END_BROWSER`: Closes the browser when the task is fully complete. Params: `{"reason": "<summary of findings>"}`
11. `SPEAK`: For simple conversation when the browser is not open. Params: `{"text": "<your_response>"}`
"""

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Sent message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text message: {e} - {response.text}")

def send_whatsapp_image(to, image_path, caption=""):
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}; files = {'file': (image_path.name, open(image_path, 'rb'), 'image/png'), 'messaging_product': (None, 'whatsapp'), 'type': (None, 'image/png')}; media_id = None
    try: response = requests.post(upload_url, headers=headers, files=files); response.raise_for_status(); media_id = response.json().get('id')
    except requests.exceptions.RequestException as e: print(f"Error uploading WhatsApp media: {e} - {response.text}"); return
    if not media_id: return
    send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
    try: requests.post(send_url, headers=headers, json=data).raise_for_status(); print(f"Sent image to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp image message: {e} - {response.text}")

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {"mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "", "user_dir": user_dir, "labeled_elements": {}, "tab_handles": {}, "is_paused": False}
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options(); options.add_argument("--headless=new"); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument("--window-size=1280,800"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options); session["driver"], session["mode"] = driver, "BROWSER"; driver.get("https://search.brave.com/"); return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"): print(f"Closing browser for session {session['user_dir'].name}"); session["driver"].quit(); session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["labeled_elements"] = {}; session["tab_handles"] = {}; session["is_paused"] = False

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    try:
        window_handles, current_handle = driver.window_handles, driver.current_window_handle; tabs, session["tab_handles"] = [], {}; [ ( (tab_id := i + 1), (session["tab_handles"][tab_id] := handle), driver.switch_to.window(handle), tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle}) ) for i, handle in enumerate(window_handles) ]
        driver.switch_to.window(current_handle); tab_info_text = "Open Tabs:\n"; [tab_info_text := tab_info_text + f"  Tab {tab['id']}: {tab['title'][:70]}{' (Current)' if tab['is_active'] else ''}\n" for tab in tabs]
    except Exception as e: print(f"Could not get tab info: {e}"); return None, "", ""
    try:
        elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS); session["labeled_elements"] = {el['label']: el for el in elements}; labels_text = "Interactive Elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in session["labeled_elements"].items()])
        png_data = driver.get_screenshot_as_png(); image = Image.open(io.BytesIO(png_data)); draw = ImageDraw.Draw(image)
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=14)
        except IOError: font = ImageFont.load_default()
        for label, el in session["labeled_elements"].items(): x, y, w, h = el['x'], el['y'], el['width'], el['height']; draw.rectangle([x, y, x + w, y + h], outline="red", width=2); draw.text((x, y - 15 if y > 15 else y), str(label), fill="red", font=font)
        image.save(screenshot_path); print(f"State captured: {len(elements)} labels, {len(tabs)} tabs."); return screenshot_path, labels_text, tab_info_text
    except Exception as e: print(f"Error getting page state: {e}"); traceback.print_exc(); return None, "", tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    global current_api_key_index
    for i in range(len(GEMINI_API_KEYS)):
        key_index_to_try = (current_api_key_index + i) % len(GEMINI_API_KEYS)
        api_key = GEMINI_API_KEYS[key_index_to_try]; print(f"Attempting API call with key #{key_index_to_try + 1}...")
        try:
            genai.configure(api_key=api_key); model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"}); chat = model.start_chat(history=chat_history)
            prompt_parts = [context_text];
            if image_path: prompt_parts.append({"mime_type": "image/png", "data": image_path.read_bytes()})
            response = chat.send_message(prompt_parts)
            print(f"API Key #{key_index_to_try + 1} succeeded."); current_api_key_index = key_index_to_try; return response.text
        except Exception as e: print(f"API Key #{key_index_to_try + 1} failed: {e}. Trying next key...")
    print("All API keys failed."); return json.dumps({"command": "END_BROWSER", "params": {"reason": "A critical internal error occurred. All API keys failed."}, "speak": "[System] My connection to the AI has failed. Please try again later."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, labels_text, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{labels_text}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else: send_whatsapp_message(from_number, "[System] Could not get a view of the page. Closing browser."); close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError: send_whatsapp_message(from_number, ai_response_text); close_browser(session) if session["mode"] == "BROWSER" else None; return
    
    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})

    # The PAUSE_AND_ASK command is special: it only sets a flag and speaks.
    if command == "PAUSE_AND_ASK":
        session["is_paused"] = True
        send_whatsapp_message(from_number, speak) # Use 'speak' as the conversational question
        return

    if speak: send_whatsapp_message(from_number, speak)

    driver = session.get("driver"); browser_was_started = False
    if command in BROWSER_COMMANDS and not driver:
        send_whatsapp_message(from_number, f"[System] Starting browser to perform: {command}...")
        driver = start_browser(session); browser_was_started = True
        if not driver: send_whatsapp_message(from_number, "[System] Fatal: Could not start browser."); close_browser(session); return

    if browser_was_started and command not in ["NAVIGATE", "BRAVE_SEARCH"]:
        send_whatsapp_message(from_number, "[System] Browser is open. Re-evaluating next step.")
        time.sleep(1); process_next_browser_step(from_number, session, "Okay, browser is open. Let's see what to do."); return

    try:
        if command in BROWSER_COMMANDS and not driver: send_whatsapp_message(from_number, "[System] Action failed because browser is not running."); return
        action_was_performed = True
        if command == "NAVIGATE": driver.get(params.get("url", "https://search.brave.com/"))
        elif command == "BRAVE_SEARCH": driver.get(f"https://search.brave.com/search?q={quote_plus(params.get('query', ''))}")
        elif command == "NEW_TAB": driver.switch_to.new_window('tab'); driver.get(params["url"]) if "url" in params and params["url"] else None
        elif command == "CLOSE_TAB":
            if len(driver.window_handles) > 1: driver.close(); driver.switch_to.window(driver.window_handles[0])
            else: send_whatsapp_message(from_number, "[System] I can't close the last tab."); action_was_performed = False
        elif command == "SWITCH_TO_TAB":
            handle = session["tab_handles"].get(params.get("tab_id"))
            if handle: driver.switch_to.window(handle)
            else: send_whatsapp_message(from_number, "[System] I couldn't find that tab ID."); action_was_performed = False
        elif command in ["TYPE", "CLICK"]:
            target_element = session["labeled_elements"].get(params.get("label"))
            if not target_element: send_whatsapp_message(from_number, f"[System] Label {params.get('label')} is not valid. Let me look again.")
            else:
                x, y = target_element['x'] + target_element['width']/2, target_element['y'] + target_element['height']/2; body = driver.find_element(By.TAG_NAME, 'body'); action = ActionChains(driver).move_to_element_with_offset(body, 0, 0).move_by_offset(x, y).click()
                if command == "TYPE": action.send_keys(params.get("text", "")).perform(); ActionChains(driver).send_keys(u'\ue007').perform() if params.get("enter") else None
                else: action.perform()
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {600 if params.get('direction', 'down') == 'down' else -600});")
        elif command == "END_BROWSER": send_whatsapp_message(from_number, f"*Summary from Magic Agent:*\n{params.get('reason', 'Task done.')}"); close_browser(session); return
        elif command == "SPEAK": return
        else: print(f"Unknown/unhandled command: {command}"); return
        if action_was_performed: time.sleep(2); process_next_browser_step(from_number, session, f"Action done: {speak}")
    except Exception as e: print(f"Error during browser action: {e}"); traceback.print_exc(); send_whatsapp_message(from_number, "[System] An action failed. Closing browser."); close_browser(session)

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN: return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)
    if request.method == 'POST':
        body = request.get_json()
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]; from_number = message_info["from"]
            if message_info.get("type") != "text": send_whatsapp_message(from_number, "[System] I only process text messages."); return Response(status=200)
            user_message_text = message_info["text"]["body"].strip(); print(f"Received from {from_number}: '{user_message_text}'")
            if user_message_text.lower() == "/stop": session = get_or_create_session(from_number); close_browser(session); send_whatsapp_message(from_number, "[System] Browser session stopped."); return Response(status=200)
            if user_message_text.lower() == "/clear":
                if from_number in user_sessions: close_browser(user_sessions.pop(from_number))
                send_whatsapp_message(from_number, "[System] Your session has been cleared."); return Response(status=200)
            session = get_or_create_session(from_number); session["chat_history"].append({"role": "user", "parts": [user_message_text]})
            if session["mode"] == "CHAT":
                session["original_prompt"] = user_message_text; ai_response = call_ai(session["chat_history"], context_text=user_message_text); process_ai_command(from_number, ai_response)
            elif session["mode"] == "BROWSER":
                if not session.get("driver"): close_browser(session); ai_response = call_ai(session["chat_history"], context_text=user_message_text); process_ai_command(from_number, ai_response); return Response(status=200)
                # Handle the "continue anyway" flow
                if session.get("is_paused"):
                    session["is_paused"] = False
                    send_whatsapp_message(from_number, "[System] Understood. Re-evaluating the page...")
                    process_next_browser_step(from_number, session, "Okay, let's try this again based on your instructions.")
                else: # Default behavior for mid-session messages
                    send_whatsapp_message(from_number, "[System] Resuming with your new instructions..."); process_next_browser_step(from_number, session, "Continuing with new instructions.")
        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
