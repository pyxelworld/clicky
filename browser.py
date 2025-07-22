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
    - **Description:** Initiates a new browser session. Use this as the very first step when a task requires web access.
    - **Params:** `{}`
    - **Example:** `{"command": "START_BROWSER", "params": {}, "thought": "The user wants me to find something online. I must start the browser first.", "speak": "Okay, opening the browser to get started."}`

2.  **`END_BROWSER`**:
    - **Description:** Closes the entire browser session. Use this ONLY when the user's task is fully complete.
    - **Params:** `{"reason": "<summary of findings or completion message>"}`
    - **Example:** `{"command": "END_BROWSER", "params": {"reason": "The temperature in London is 15°C. I have found the answer."}, "thought": "The task is complete. I will now close the browser and provide the final answer.", "speak": "All done! Here is the information you requested."}`

**== NAVIGATION COMMANDS ==**

3.  **`NAVIGATE`**:
    - **Description:** Goes directly to a specific URL in the current tab. Most efficient way to visit a known website.
    - **Params:** `{"url": "<full_url>"}`
    - **Example:** `{"command": "NAVIGATE", "params": {"url": "https://www.github.com"}, "thought": "The user wants to go to GitHub. Navigating directly is the best way.", "speak": "Heading over to GitHub now."}`

4.  **`BRAVE_SEARCH`**:
    - **Description:** Performs a Brave search in the current tab. This is much faster than loading the site and typing manually.
    - **Params:** `{"query": "<search_term>"}`
    - **Example:** `{"command": "BRAVE_SEARCH", "params": {"query": "latest news on AI"}, "thought": "The user wants to search for news. Using the BRAVE_SEARCH command is the most direct method.", "speak": "Searching Brave for 'latest news on AI' for you."}`

**== PAGE INTERACTION COMMANDS ==**

5.  **`CLICK`**:
    - **Description:** Clicks an element on the page, identified by its label number from the screenshot.
    - **Params:** `{"label": <int>}`
    - **Example:** `{"command": "CLICK", "params": {"label": 12}, "thought": "Label 12 is the 'Next Page' link, which I need to click to see more results.", "speak": "Clicking the 'Next Page' link."}`

6.  **`TYPE`**:
    - **Description:** Types text where the cursor is currently located. **IMPORTANT: You MUST use the `CLICK` command on a text field *before* using `TYPE`.**
    - **Params:** `{"text": "<text_to_type>", "enter": <true/false>}` (set "enter" to true to press Enter after typing)
    - **Example:** `{"command": "TYPE", "params": {"text": "my-username", "enter": false}, "thought": "I have already clicked the username input field. Now I will type the username into it.", "speak": "Typing in the username."}`

7.  **`SCROLL`**:
    - **Description:** Scrolls the current page up or down to see more content.
    - **Params:** `{"direction": "<up|down>"}`
    - **Example:** `{"command": "SCROLL", "params": {"direction": "down"}, "thought": "The information I need is likely further down the page. I will scroll.", "speak": "Scrolling down to see more..."}`

**== TAB MANAGEMENT COMMANDS ==**

8.  **`NEW_TAB`**:
    - **Description:** Opens a new browser tab.
    - **Params:** `{"url": "<optional_url_to_open>"}` (If URL is provided, the new tab will open directly to it).
    - **Example:** `{"command": "NEW_TAB", "params": {"url": "https://en.wikipedia.org"}, "thought": "I need to look something up on Wikipedia without losing my current page. I'll open it in a new tab.", "speak": "Opening Wikipedia in a new tab."}`

9.  **`SWITCH_TO_TAB`**:
    - **Description:** Switches focus to a different open tab. Use the `tab_id` provided in the context.
    - **Params:** `{"tab_id": <int>}`
    - **Example:** `{"command": "SWITCH_TO_TAB", "params": {"tab_id": 1}, "thought": "I am finished on the current tab and need to return to the first tab to continue the task.", "speak": "Switching back to the first tab."}`

10. **`CLOSE_TAB`**:
    - **Description:** Closes the **currently active** tab.
    - **Params:** `{}`
    - **Example:** `{"command": "CLOSE_TAB", "params": {}, "thought": "I have extracted the necessary information from this tab and no longer need it. I will close it to reduce clutter.", "speak": "Closing the current tab."}`

**== USER INTERACTION COMMANDS ==**

11. **`PAUSE_AND_ASK`**:
    - **Description:** Use this command if you are blocked, unsure what to do next, or need more information from the user (e.g., a username, a password, or a choice to make). This will pause the task and send your question to the user. The user's next message will be your answer.
    - **Params:** `{"question": "<your_question_for_the_user>"}`
    - **Example:** `{"command": "PAUSE_AND_ASK", "params": {"question": "I've landed on the login page. What username should I use?"}, "thought": "I can't proceed without a username. I must ask the user.", "speak": "I need a little help. What username should I use here?"}`

12. **`SPEAK`**:
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
            "user_dir": user_dir, "labeled_elements": {}, "tab_handles": {}
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    """Starts a new Selenium browser instance for a session."""
    if session.get("driver"):
        return session["driver"]
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
        print(f"Browser started for session {session['user_dir'].name}")
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        traceback.print_exc()
        return None

def close_browser(session):
    """Closes the Selenium browser and resets session state."""
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try:
            session["driver"].quit()
        except Exception:
            pass
        session["driver"] = None
    session["mode"] = "CHAT"
    session["original_prompt"] = ""
    session["labeled_elements"] = {}
    session["tab_handles"] = {}

def get_page_state(driver, session):
    """Gets screenshot, labels (using Selenium), and tab info."""
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    
    # 1. Get Tab Info
    tab_info_text = "No open tabs."
    try:
        window_handles = driver.window_handles
        current_handle = driver.current_window_handle
        tabs = []
        session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1
            session["tab_handles"][tab_id] = handle
            driver.switch_to.window(handle)
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        
        driver.switch_to.window(current_handle)

        tab_info_text = "Open Tabs:\n"
        for tab in tabs:
            active_marker = " (Current)" if tab["is_active"] else ""
            tab_info_text += f"  Tab {tab['id']}: {tab['title'][:70]}{active_marker}\n"
    except Exception as e:
        print(f"Could not get tab info: {e}")
        return None, "", ""
    
    # 2. Get Labeled Screenshot using Selenium finders (more robust)
    try:
        # Define viewport dimensions
        viewport_height = driver.execute_script("return window.innerHeight")
        viewport_width = driver.execute_script("return window.innerWidth")

        # Find all potential interactive elements
        selector = 'a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        
        session["labeled_elements"] = {}
        label_counter = 1
        visible_elements_for_drawing = []

        for elem in elements:
            if not elem.is_displayed():
                continue
            
            rect = elem.rect
            # Check if element is within the viewport
            if rect['y'] < viewport_height and rect['x'] < viewport_width and \
               (rect['y'] + rect['height']) > 0 and (rect['x'] + rect['width']) > 0:
                
                text = (elem.text or elem.get_attribute('value') or elem.get_attribute('aria-label') or elem.get_attribute('placeholder') or "").strip().replace('\s+', ' ').substring(0, 50)
                
                element_data = {
                    'webelement': elem, # Store the actual WebElement
                    'x': rect['x'],
                    'y': rect['y'],
                    'width': rect['width'],
                    'height': rect['height'],
                    'tag': elem.tag_name,
                    'text': text
                }
                session["labeled_elements"][label_counter] = element_data
                visible_elements_for_drawing.append((label_counter, element_data))
                label_counter += 1

        labels_text = "Interactive Elements:\n" + "\n".join([f"  {label}: {data['tag']} '{data['text']}'" for label, data in visible_elements_for_drawing])
        
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=14)
        except IOError:
            font = ImageFont.load_default()
        
        for label, data in visible_elements_for_drawing:
            x, y, w, h = data['x'], data['y'], data['width'], data['height']
            draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
            draw.text((x, y - 15 if y > 15 else y), str(label), fill="red", font=font)
        
        image.save(screenshot_path)
        print(f"State captured: {len(session['labeled_elements'])} labels, {len(tabs)} tabs.")
        return screenshot_path, labels_text, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}")
        traceback.print_exc()
        return None, "", tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    """Calls the Gemini AI with the full context, rotating API keys on failure."""
    prompt_parts = [context_text]
    if image_path:
        try:
            img_part = {"mime_type": "image/png", "data": image_path.read_bytes()}
            prompt_parts.append(img_part)
        except Exception as e:
            return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: Could not read the screenshot file. {e}"}, "thought": "The image file for the screenshot could not be read. I must end the session.", "speak": "Sorry, I'm having trouble seeing the screen. Let's stop for now."})
    
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
        except Exception as e:
            print(f"API key #{i+1} failed. Error: {e}")
            last_error = e
            continue
    
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: All API keys failed. Last error: {last_error}"}, "thought": "All my connections to the AI brain are failing. I cannot continue.", "speak": "Sorry, I'm having trouble connecting to my AI brain right now. Let's stop for now."})

def process_next_browser_step(from_number, session, caption):
    """Shared logic for taking a screenshot, getting context, and calling the AI in browser mode."""
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
    """Parses AI response and executes the corresponding action."""
    session = get_or_create_session(from_number)
    try:
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        if session["mode"] == "BROWSER":
            close_browser(session)
        return

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak:
        send_whatsapp_message(from_number, speak)

    driver = session.get("driver")

    if command == "START_BROWSER":
        driver = start_browser(session)
        if not driver:
            send_whatsapp_message(from_number, "Could not open browser.")
            close_browser(session)
            return
        time.sleep(1)
        driver.get("https://search.brave.com")
        time.sleep(1)
        process_next_browser_step(from_number, session, "Browser started at Brave.com. What's next?")
        return

    if not driver and command not in ["SPEAK", "START_BROWSER"]:
        send_whatsapp_message(from_number, "Browser isn't running. Please start a task first.")
        return

    try:
        action_was_performed = True
        if command == "NAVIGATE":
            driver.get(params.get("url", "https://search.brave.com"))
        elif command == "BRAVE_SEARCH":
            query = quote_plus(params.get("query", ""))
            driver.get(f"https://search.brave.com/search?q={query}")
        elif command == "NEW_TAB":
            driver.switch_to.new_window('tab')
            if "url" in params and params["url"]:
                driver.get(params["url"])
        elif command == "CLOSE_TAB":
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            else:
                send_whatsapp_message(from_number, "I can't close the last tab.")
                action_was_performed = False
        elif command == "SWITCH_TO_TAB":
            handle = session["tab_handles"].get(params.get("tab_id"))
            if handle:
                driver.switch_to.window(handle)
            else:
                send_whatsapp_message(from_number, "I couldn't find that tab ID.")
                action_was_performed = False
        elif command == "CLICK":
            label = params.get("label")
            target_element_data = session["labeled_elements"].get(label)
            if not target_element_data:
                send_whatsapp_message(from_number, f"Label {label} is not valid. Let me look again.")
                action_was_performed = False
            else:
                element_to_click = target_element_data['webelement']
                element_to_click.click() # More robust click
        elif command == "TYPE":
            action = ActionChains(driver)
            action.send_keys(params.get("text", ""))
            if params.get("enter"):
                action.send_keys(u'\ue007')
            action.perform()
        elif command == "SCROLL":
            scroll_amount = 600 if params.get('direction', 'down') == 'down' else -600
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        elif command == "END_BROWSER":
            send_whatsapp_message(from_number, f"*Summary from Magic Agent:*\n{params.get('reason', 'Task done.')}")
            close_browser(session)
            return
        elif command == "PAUSE_AND_ASK":
            return
        elif command == "SPEAK":
            return
        else:
            print(f"Unknown command received: {command}")
            send_whatsapp_message(from_number, f"I received an unknown command '{command}'. Let me look at the page again.")
        
        if action_was_performed:
            time.sleep(2)
            process_next_browser_step(from_number, session, f"Action done: {speak}")

    except Exception as e:
        print(f"Error during browser action: {e}")
        traceback.print_exc()
        if "element is not attached" in str(e):
             send_whatsapp_message(from_number, "The page changed before I could act. Let me look again.")
             time.sleep(2)
             process_next_browser_step(from_number, session, "Page reloaded, trying again.")
        else:
            send_whatsapp_message(from_number, f"An action failed with an error. I'm closing the browser for safety.")
            close_browser(session)

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
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I only process text messages.")
                return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
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
        except (KeyError, IndexError, TypeError):
            pass
        except Exception as e:
            print(f"Error processing webhook: {e}")
            traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
