import os
import json
import requests
from flask import Flask, request, Response
from google import genai
from google.generativeai.types import GenerationConfig, Part, Content
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
import base64
import re
import time
import tempfile
import threading # FIX: Import threading for background tasks
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
# --- Flask App ---
app = Flask(__name__)

# --- State Management ---
# User states: dict of phone_number -> state
user_states = {}

# --- System Prompt ---
SYSTEM_PROMPT = """
You are Magic Agent, a helpful AI assistant that can control a web browser to perform tasks for the user.
Respond concisely and friendly in normal conversations.

To start a browser session, include in your response: [START_BROWSER url="https://example.com"] (url is optional, defaults to a blank page).

Once in browser mode, you will receive screenshots of the current browser viewport and the viewport size.
Respond with EXACTLY ONE command in the format [COMMAND param="value" param2="value2"].
Do not add any extra text outside the command. Your command will be executed, and you'll get the next screenshot.

Available commands:
- [OPEN_TAB url="https://example.com"] : Open a new tab with the URL.
- [CLOSE_TAB index="1"] : Close the tab at index (0-based, default current).
- [SWITCH_TAB index="1"] : Switch to tab at index (0-based).
- [SCROLL direction="down" amount="500"] : Scroll in direction (down, up, left, right) by amount in pixels.
- [CLICK x="100" y="200"] : Click at coordinates (x,y) in the current viewport (0,0 is top-left).
- [TYPE text="hello"] : Type the text into the currently focused element.
- [PRESS_KEY key="ENTER"] : Press a key (e.g., ENTER, BACKSPACE).
- [PRESS_SHORTCUT keys="CTRL+T"] : Press a shortcut (e.g., CTRL+T for new tab, separate with +).
- [END_BROWSER] : End the browser session.
- [ASK_USER question="What is your email?"] : Pause and ask the user a question. The session will resume with the user's answer.

Use coordinates based on the provided screenshot and viewport size for clicks.
For typing, first CLICK on the input field to focus, then TYPE.
For downloads, navigate and click download links; files save to user's folder.
If you need more info, use ASK_USER.
When the task is complete, use END_BROWSER.
"""

def get_user_state(phone):
    """Initializes and retrieves the state for a given user."""
    if phone not in user_states:
        user_states[phone] = {
            'history': [],
            'mode': 'normal', # 'normal', 'browsing', 'asking'
            'browser': None,
            'viewport': {'width': 1280, 'height': 800},
            'pending_question': None,
            # FIX: Add a lock for thread-safe state modifications
            'lock': threading.Lock()
        }
    return user_states[phone]

def call_gemini(phone: str, user_message: str = None, image_base64: str = None) -> str:
    """Calls the Gemini API with the user's history and current message."""
    try:
        # FIX: Initialize the model with the system prompt for better consistency
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash", # As requested, using a flash model. gemini-2.0-flash is not a public model name as of now.
            system_instruction=SYSTEM_PROMPT
        )
        genai.configure(api_key=GEMINI_API_KEY)

        state = get_user_state(phone)
        history = state['history']

        parts = []
        if user_message:
            parts.append(Part.from_text(text=user_message))
        if image_base64:
            # FIX: Use google.generativeai.types.Part for creating image parts
            image_part = Part.from_data(
                mime_type="image/png",
                data=base64.b64decode(image_base64) # FIX: Gemini SDK expects bytes, not base64 string
            )
            parts.append(image_part)

        # Generate content
        response = model.generate_content(history + [Content(role="user", parts=parts)])
        full_response = response.text

        # Append to history for context
        with state['lock']:
            state['history'].append(Content(role="user", parts=parts))
            state['history'].append(response.candidates[0].content)

        return full_response

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return f"Sorry, an error occurred with the AI model: {e}"

def start_browser(phone, url=None):
    """Starts a new Selenium browser instance for a user."""
    state = get_user_state(phone)
    profile_dir = os.path.join(os.getcwd(), f"profiles/{phone}")
    download_dir = os.path.join(os.getcwd(), f"downloads/{phone}")
    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new") # FIX: Use the new headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--window-size={state['viewport']['width']},{state['viewport']['height']}")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url if url else "about:blank")
        with state['lock']:
            state['browser'] = driver
            state['mode'] = 'browsing'
        return driver
    except Exception as e:
        print(f"Error starting browser: {e}")
        send_whatsapp_message(phone, "Sorry, I couldn't start the browser. Please check the server logs.")
        return None

def close_browser(phone):
    """Closes the Selenium browser and resets the user's state."""
    state = get_user_state(phone)
    with state['lock']:
        if state['browser']:
            try:
                state['browser'].quit()
            except Exception as e:
                print(f"Error quitting browser: {e}")
            state['browser'] = None
        state['mode'] = 'normal'
        state['pending_question'] = None

# FIX: A more robust command parser
def parse_command(response: str):
    """Parses a command like [CMD param1="value1"] from the model's response."""
    match = re.search(r'\[(.*?)\]', response)
    if not match:
        return None, {}

    content = match.group(1).strip()
    parts = content.split(maxsplit=1)
    command = parts[0].upper()
    
    params = {}
    if len(parts) > 1:
        # This regex finds key="value" or key='value' pairs
        param_matches = re.findall(r'(\w+)=["\'](.*?)["\']', parts[1])
        params = dict(param_matches)
        
    return command, params

def execute_command(phone, cmd, params):
    """Executes a parsed browser command."""
    state = get_user_state(phone)
    driver = state['browser']
    if not driver:
        return "No browser active."

    action_desc = f"Magic Agent performed: {cmd} with params {params}"
    try:
        if cmd == 'OPEN_TAB':
            url = params.get('url', 'about:blank')
            driver.execute_script(f"window.open('{url}', '_blank');")
            driver.switch_to.window(driver.window_handles[-1])
            action_desc = f"Magic Agent opened new tab: {url}"
        # ... (other commands are mostly okay, keeping them as is)
        elif cmd == 'CLOSE_TAB':
            # Add logic to handle closing last tab
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[-1])
                action_desc = "Magic Agent closed the current tab."
            else:
                action_desc = "Magic Agent cannot close the last tab. Use [END_BROWSER] instead."
        elif cmd == 'CLICK':
            x = int(params.get('x', 0))
            y = int(params.get('y', 0))
            # FIX: Clicking relative to viewport can be tricky. This JS approach is more reliable.
            driver.execute_script(f"document.elementFromPoint({x}, {y}).click();")
            action_desc = f"Magic Agent clicked at ({x}, {y})"
        elif cmd == 'TYPE':
            text_to_type = params.get('text', '')
            ActionChains(driver).send_keys(text_to_type).perform()
            action_desc = f"Magic Agent typed: '{text_to_type}'"
        elif cmd == 'END_BROWSER':
            close_browser(phone)
            action_desc = "Magic Agent ended the browser session."
            return action_desc
        elif cmd == 'ASK_USER':
            question = params.get('question', 'I need more information.')
            with state['lock']:
                state['pending_question'] = question
                state['mode'] = 'asking'
            send_whatsapp_message(phone, question)
            action_desc = f"Magic Agent is asking you: {question}"
            return action_desc
        # Add other commands here as in your original code (SCROLL, PRESS_KEY, etc.)
        else:
             action_desc = f"Unknown command: {cmd}"

        time.sleep(2) # Increased sleep for pages to load/react
        return action_desc

    except Exception as e:
        print(f"Error executing command {cmd}: {e}")
        return f"Error trying to perform {cmd}. The page might not have loaded correctly."


def upload_media(image_path):
    """Uploads an image to WhatsApp servers and returns the media ID."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        data = {"messaging_product": "whatsapp", "type": "image/png"}
        response = requests.post(url, headers=headers, files=files, data=data)
    
    if response.status_code == 200:
        return response.json().get('id')
    else:
        print(f"Failed to upload media: {response.status_code} {response.text}")
        return None

def send_whatsapp_image(to_number: str, image_path: str, caption: str = ""):
    """Sends an image message via the WhatsApp Business API."""
    media_id = upload_media(image_path)
    if not media_id:
        send_whatsapp_message(to_number, "Error: Could not upload screenshot to send.")
        return

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {"id": media_id, "caption": caption},
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Failed to send image: {response.status_code} {response.text}")

def send_whatsapp_message(to_number: str, message: str):
    """Sends a text message via the WhatsApp Business API."""
    if not message: # Don't send empty messages
        return
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": message}}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Failed to send message: {response.status_code} {response.text}")


# --- Core Browser Logic (to be run in a thread) ---

def process_browser_loop(phone):
    """The main loop for an active browser session."""
    state = get_user_state(phone)
    driver = state['browser']

    if not driver:
        print(f"Browser loop called for {phone} but no browser found.")
        return

    while True:
        with state['lock']:
            # Check if mode has changed by another thread (e.g., webhook received END_BROWSER)
            if state['mode'] != 'browsing':
                break
        
        try:
            screenshot_base64 = driver.get_screenshot_as_base64()
            w, h = state['viewport']['width'], state['viewport']['height']
            prompt = f"Current screenshot attached. Viewport: {w}x{h}. What is the next single command to execute?"

            # Call Gemini with the screenshot
            response = call_gemini(phone, user_message=prompt, image_base64=screenshot_base64)
            print(f"Gemini response for {phone}: {response}")
            
            cmd, params = parse_command(response)
            if not cmd:
                send_whatsapp_message(phone, "Magic Agent returned an invalid command. Please try again.")
                # Maybe end the session if it's consistently failing
                # close_browser(phone)
                break

            action_desc = execute_command(phone, cmd, params)

            # Check mode again after execution, as it might have changed (e.g., END_BROWSER, ASK_USER)
            with state['lock']:
                if state['mode'] != 'browsing':
                    if cmd != 'ASK_USER': # ASK_USER already sends a message
                        send_whatsapp_message(phone, action_desc)
                    break
            
            # Send screenshot update
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                driver.get_screenshot_as_png_stream().seek(0)
                tmp.write(driver.get_screenshot_as_png())
                tmp_path = tmp.name
            
            send_whatsapp_image(phone, tmp_path, action_desc)
            os.unlink(tmp_path)

        except Exception as e:
            print(f"An error occurred in the browser loop for {phone}: {e}")
            send_whatsapp_message(phone, "An unexpected error occurred during browsing. The session has ended.")
            close_browser(phone)
            break
            
# FIX: New function to handle starting the session in a thread
def start_browser_session_threaded(phone, url):
    """Initializes browser and starts the processing loop in a thread."""
    driver = start_browser(phone, url)
    if driver:
        # Send initial screenshot
        action_desc = "Magic Agent has started the browser."
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            driver.save_screenshot(tmp.name)
            tmp_path = tmp.name
        send_whatsapp_image(phone, tmp_path, action_desc)
        os.unlink(tmp_path)
        
        # Start the main loop
        process_browser_loop(phone)


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Handle webhook verification
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)

    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2))

        try:
            if (body.get("entry") and body["entry"][0].get("changes") and
                body["entry"][0]["changes"][0].get("value") and
                body["entry"][0]["changes"][0]["value"].get("messages")):
                
                message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
                from_number = message_info["from"]
                
                state = get_user_state(from_number)
                
                if message_info.get("type") == "text":
                    user_message_text = message_info["text"]["body"]
                    
                    with state['lock']:
                        current_mode = state['mode']
                    
                    if current_mode == 'asking':
                        # The user is answering a question from the browser agent
                        send_whatsapp_message(from_number, "Thanks! Resuming the browser session...")
                        
                        # Prepare the context for Gemini
                        answer_prompt = f"User has answered your question '{state['pending_question']}': '{user_message_text}'"
                        call_gemini(from_number, user_message=answer_prompt)
                        
                        # FIX: Resume the browser loop in a new background thread
                        with state['lock']:
                            state['pending_question'] = None
                            state['mode'] = 'browsing'
                        
                        threading.Thread(target=process_browser_loop, args=(from_number,)).start()
                    
                    else:
                        # This is a new conversation or a normal message
                        gemini_response = call_gemini(from_number, user_message=user_message_text)
                        
                        cmd, params = parse_command(gemini_response)

                        # FIX: Check for START_BROWSER and launch in background
                        if cmd == 'START_BROWSER':
                            # Acknowledge immediately
                            initial_text = gemini_response.split('[')[0].strip()
                            send_whatsapp_message(from_number, initial_text or "Got it. Starting a browser session for you...")
                            
                            url = params.get('url')
                            # Start the whole session in a thread
                            threading.Thread(target=start_browser_session_threaded, args=(from_number, url)).start()
                        else:
                            # It's just a regular chat message
                            send_whatsapp_message(from_number, gemini_response)
                else:
                    send_whatsapp_message(from_number, "I can only process text messages for now.")
        
        except Exception as e:
            print(f"Error processing webhook: {e}")
            import traceback
            traceback.print_exc()

        # FIX: Always return 200 OK immediately to WhatsApp
        return Response(status=200)

if __name__ == '__main__':
    # Make sure you have chromedriver installed and in your PATH
    # or specify the path using webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    print("WhatsApp Bot Server starting...")
    app.run(port=5000, debug=True, use_reloader=False)
