import os
import json
import requests
import time
import io
import traceback
from flask import Flask, request, Response
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
# NEW TOKEN AS PROVIDED
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- AI MODEL CONFIGURATION ---
AI_MODEL_NAME = "gemini-1.5-flash"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

user_sessions = {}

# --- JAVASCRIPT FOR ELEMENT LABELING ---
JS_GET_INTERACTIVE_ELEMENTS = """
    const elements = Array.from(document.querySelectorAll(
        'a, button, input:not([type="hidden"]), textarea, [role="button"], [role="link"], [onclick]'
    ));
    const interactiveElements = [];
    for (let i = 0; i < elements.length; i++) {
        const elem = elements[i];
        const rect = elem.getBoundingClientRect();
        // Filter out invisible or very small elements
        if (rect.width > 5 && rect.height > 5 && rect.top >= 0 && rect.left >= 0) {
            let text = (elem.innerText || elem.value || elem.getAttribute('aria-label') || elem.getAttribute('placeholder') || 'No text').trim().substring(0, 50);
            interactiveElements.push({
                label: i + 1,
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
                tag: elem.tagName.toLowerCase(),
                text: text
            });
        }
    }
    return interactiveElements;
"""

# --- SYSTEM PROMPT (UPDATED FOR ELEMENT LABELING) ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly intelligent AI assistant that controls a web browser. You operate in two modes: CHAT and BROWSER. Your responses MUST ALWAYS be in a JSON format.

**Interaction Model:**
When in BROWSER mode, you will receive a screenshot where interactive elements (links, buttons, inputs) are marked with a numbered red box. You must choose the number of the element you want to interact with.

**JSON Response Structure:**
{
  "command": "COMMAND_NAME",
  "params": { ... },
  "thought": "Your reasoning for choosing this command and element.",
  "speak": "A short, user-friendly message describing your action."
}

--- AVAILABLE COMMANDS ---

1.  **Start Browser Session:**
    - `command`: "START_BROWSER"
    - `params`: {}

2.  **Type Text:**
    - Description: Types text into an input field or textarea identified by its label number.
    - `command`: "TYPE"
    - `params`: {"label": <int>, "text": "<text_to_type>", "enter": <true/false>}
    - Example: `{"command": "TYPE", "params": {"label": 5, "text": "weather in london", "enter": true}, "thought": "The user wants to search. Label 5 is the search input field. I will type the query and press enter.", "speak": "Typing 'weather in london' into the search bar."}`

3.  **Click Element:**
    - Description: Clicks on an element identified by its label number.
    - `command`: "CLICK"
    - `params`: {"label": <int>}
    - Example: `{"command": "CLICK", "params": {"label": 8}, "thought": "Label 8 is the 'Search' button. I need to click it to proceed.", "speak": "Clicking the search button."}`

4.  **Scroll Page:**
    - Description: Scrolls the page 'up' or 'down'. No label needed.
    - `command`: "SCROLL"
    - `params`: {"direction": "<up|down>"}

5.  **End Browser Session:**
    - Description: Closes the browser and summarizes findings.
    - `command`: "END_BROWSER"
    - `params`: {"reason": "<summary_of_findings>"}

6.  **Ask User for Information:**
    - Description: Pauses the browser session to ask the user for clarification.
    - `command`: "PAUSE_AND_ASK"
    - `params`: {"question": "What should I do next?"}

7.  **Answer Directly (Chat Mode):**
    - Description: Used in CHAT mode for simple conversation.
    - `command`: "SPEAK"
    - `params`: {"text": "Your response to the user."}
"""

genai.configure(api_key=GEMINI_API_KEY)

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
    media_id = None
    try:
        response = requests.post(upload_url, headers=headers, files=files)
        response.raise_for_status()
        media_id = response.json().get('id')
    except requests.exceptions.RequestException as e:
        print(f"Error uploading WhatsApp media: {e} - {response.text}")
        return
    if not media_id: return
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
            "user_dir": user_dir, "downloads_dir": user_dir / "downloads",
            "profile_dir": user_dir / "profile", "labeled_elements": {}
        }
        session["downloads_dir"].mkdir(parents=True, exist_ok=True)
        session["profile_dir"].mkdir(parents=True, exist_ok=True)
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
    options.add_argument(f"--user-data-dir={session['profile_dir']}")
    prefs = {"download.default_directory": str(session['downloads_dir'])}
    options.add_experimental_option("prefs", prefs)
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver
        session["mode"] = "BROWSER"
        print(f"Browser started for session {session['user_dir'].name}")
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc()
        return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except Exception: pass
        session["driver"] = None
    session["mode"] = "CHAT"
    session["original_prompt"] = ""
    session["labeled_elements"] = {}

def take_screenshot_with_labels(driver, session):
    """Takes screenshot, finds elements, draws labels, and stores element data."""
    screenshot_path = session["user_dir"] / f"screenshot_{int(time.time())}.png"
    try:
        elements = driver.execute_script(JS_GET_INTERACTIVE_ELEMENTS)
        session["labeled_elements"] = {el['label']: el for el in elements}

        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=14)
        except IOError: font = ImageFont.load_default()

        for label, el in session["labeled_elements"].items():
            x, y, w, h = el['x'], el['y'], el['width'], el['height']
            draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
            draw.text((x, y - 15 if y > 15 else y), str(label), fill="red", font=font)
        
        image.save(screenshot_path)
        print(f"Screenshot with {len(elements)} labels saved to {screenshot_path}")
        return screenshot_path, session["labeled_elements"]
    except Exception as e:
        print(f"Error taking screenshot with labels: {e}"); traceback.print_exc()
        return None, {}

def call_ai(chat_history, labels_text="", image_path=None):
    model = genai.GenerativeModel(
        AI_MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"}
    )
    chat = model.start_chat(history=chat_history)
    
    last_user_message = chat_history[-1]['parts'][0] if chat_history and chat_history[-1]['role'] == 'user' else ""
    prompt_content = f"{last_user_message}\n{labels_text}"
    prompt_parts = [prompt_content]

    if image_path:
        print(f"AI Call: Vision mode with image {image_path.name}")
        try:
            img_part = {"mime_type": "image/png", "data": image_path.read_bytes()}
            prompt_parts.append(img_part)
        except Exception as e:
            print(f"Error reading image file for AI: {e}")
            return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error reading screen image: {e}"}, "thought": "Image read failed.", "speak": "Error with screen view."})
    else:
        print("AI Call: Chat mode")
    
    try:
        response = chat.send_message(prompt_parts)
        return response.text
    except Exception as e:
        print(f"CRITICAL: Error calling Gemini API: {e}")
        return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI model error: {e}"}, "thought": "AI API failed.", "speak": "Error connecting to my brain."})

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    try:
        print(f"AI Response: {ai_response_text}")
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, ai_response_text)
        session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
        if session["mode"] == "BROWSER":
             send_whatsapp_message(from_number, "Internal command error. Closing browser.")
             close_browser(session)
        return

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)

    if command == "START_BROWSER":
        driver = start_browser(session)
        if not driver:
            send_whatsapp_message(from_number, "Could not open browser.")
            close_browser(session)
            return
        time.sleep(1)
        # Go to a default page
        driver.get("https://www.google.com")
        time.sleep(1)
        process_next_browser_step(from_number, session, "Browser started. What's next?")
    
    elif command in ["TYPE", "CLICK", "SCROLL"] and session["mode"] == "BROWSER":
        driver = session.get("driver")
        if not driver:
            send_whatsapp_message(from_number, "Browser lost. Please start over."); close_browser(session); return
        try:
            if command in ["TYPE", "CLICK"]:
                label = params.get("label")
                target_element = session["labeled_elements"].get(label)
                if not target_element:
                    send_whatsapp_message(from_number, f"I tried to use label {label}, but it's not valid. Let me look again.")
                    process_next_browser_step(from_number, session, "Invalid label chosen, retrying.")
                    return
                
                # Center of the element for more reliable clicking
                x = target_element['x'] + target_element['width'] / 2
                y = target_element['y'] + target_element['height'] / 2
                body = driver.find_element(By.TAG_NAME, 'body')
                action = ActionChains(driver).move_to_element_with_offset(body, 0, 0).move_by_offset(x, y).click()

                if command == "TYPE":
                    action.send_keys(params.get("text", ""))
                    if params.get("enter"):
                        action.send_keys(u'\ue007') # Enter key
                action.perform()

            elif command == "SCROLL":
                scroll_amount = 600 if params.get('direction', 'down') == 'down' else -600
                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

            time.sleep(2)
            process_next_browser_step(from_number, session, f"Action done: {speak}")
        except Exception as e:
            print(f"Error during browser action: {e}"); traceback.print_exc()
            send_whatsapp_message(from_number, f"Action failed: {e}. Closing browser.")
            close_browser(session)

    elif command == "PAUSE_AND_ASK": send_whatsapp_message(from_number, params.get("question", "I need info."))
    elif command == "END_BROWSER":
        send_whatsapp_message(from_number, f"*Summary from Magic Agent:*\n{params.get('reason', 'Task done.')}")
        close_browser(session)
    elif command == "SPEAK": pass
    else:
        print(f"Unknown command: {command}")
        if session["mode"] == "BROWSER": close_browser(session)

def process_next_browser_step(from_number, session, caption):
    """Shared logic for taking a screenshot and calling the AI in browser mode."""
    screenshot_path, labeled_elements = take_screenshot_with_labels(session["driver"], session)
    if screenshot_path:
        labels_text = "Interactive elements:\n" + "\n".join([f"  {l}: {e['tag']} '{e['text']}'" for l, e in labeled_elements.items()])
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], labels_text=labels_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "Could not get a view of the page. Closing browser.")
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
                ai_response = call_ai(session["chat_history"])
                process_ai_command(from_number, ai_response)
            elif session["mode"] == "BROWSER":
                driver = session.get("driver")
                if not driver:
                    close_browser(session)
                    ai_response = call_ai(session["chat_history"])
                    process_ai_command(from_number, ai_response)
                    return Response(status=200)
                
                send_whatsapp_message(from_number, "Okay, using that info to continue...")
                process_next_browser_step(from_number, session, "Continuing with new instructions.")
        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
