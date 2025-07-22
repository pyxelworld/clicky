import os
import json
import requests
from flask import Flask, request, Response
from google import genai
from google.genai import types
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
import base64
import re
import time
import tempfile
import multipart  # Note: You may need to install requests-toolbelt for better multipart handling, but using requests post with files.

# Constants
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# Flask app
app = Flask(__name__)

# User states: dict of phone_number -> state
user_states = {}

# System prompt for Magic Agent
SYSTEM_PROMPT = """
You are Magic Agent, a helpful AI assistant that can control a web browser to perform tasks for the user.
Respond concisely and friendly in normal conversations.

To start a browser session, include in your response: [START_BROWSER url="https://example.com"] (url is optional, defaults to blank page).

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
When task is complete, use END_BROWSER.
"""

def get_user_state(phone):
    if phone not in user_states:
        user_states[phone] = {
            'history': [],
            'mode': 'normal',
            'browser': None,
            'viewport': {'width': 1280, 'height': 800},
            'pending_question': None
        }
    return user_states[phone]

def call_gemini(phone: str, user_message: str = None, image_base64: str = None, is_browser_mode: bool = False) -> str:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "gemini-2.0-flash"

        state = get_user_state(phone)
        history = state['history']

        parts = []
        if user_message:
            parts.append(types.Part.from_text(text=user_message))
        if image_base64:
            parts.append(types.Part.from_data(mime_type="image/png", data=image_base64))

        new_content = types.Content(role="user", parts=parts) if parts else None

        contents = history.copy()
        if new_content:
            contents.append(new_content)

        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text=SYSTEM_PROMPT),
            ],
        )

        response_chunks = []
        for chunk in client.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=generate_content_config,
        ):
            response_chunks.append(chunk.text)

        full_response = "".join(response_chunks)

        # Append to history
        if new_content:
            state['history'].append(new_content)
        state['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=full_response)]))

        return full_response

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "Sorry, an error occurred."

def start_browser(phone, url=None):
    state = get_user_state(phone)
    profile_dir = f"profiles/{phone}"
    download_dir = f"downloads/{phone}"
    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--window-size=1280,800")
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    driver = webdriver.Chrome(options=options)
    if url:
        driver.get(url)
    else:
        driver.get("about:blank")

    state['browser'] = driver
    state['mode'] = 'browsing'
    return driver

def close_browser(phone):
    state = get_user_state(phone)
    if state['browser']:
        state['browser'].quit()
        state['browser'] = None
    state['mode'] = 'normal'
    state['pending_question'] = None

def take_screenshot(driver):
    return driver.get_screenshot_as_base64()

def save_screenshot(driver, path):
    driver.save_screenshot(path)

def parse_command(response):
    # Find [COMMAND ...] in response
    match = re.search(r'\[([^\]]+)\]', response)
    if not match:
        return None, {}
    cmd_str = match.group(1)
    parts = re.findall(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', cmd_str)
    cmd = parts[0][0] if parts else cmd_str.split()[0]
    params = {}
    for p in parts[1:]:
        key = p[0]
        value = p[1] or p[2] or p[3]
        params[key] = value
    return cmd, params

def execute_command(phone, cmd, params):
    state = get_user_state(phone)
    driver = state['browser']
    if not driver:
        return "No browser active."

    action_desc = f"Magic Agent performed: {cmd} with params {params}"
    if cmd == 'OPEN_TAB':
        url = params.get('url', 'about:blank')
        driver.execute_script(f"window.open('{url}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        action_desc = f"Magic Agent opened new tab: {url}"

    elif cmd == 'CLOSE_TAB':
        index = int(params.get('index', len(driver.window_handles) - 1))
        if index < len(driver.window_handles):
            driver.switch_to.window(driver.window_handles[index])
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        action_desc = f"Magic Agent closed tab {index}"

    elif cmd == 'SWITCH_TAB':
        index = int(params.get('index', 0))
        if index < len(driver.window_handles):
            driver.switch_to.window(driver.window_handles[index])
        action_desc = f"Magic Agent switched to tab {index}"

    elif cmd == 'SCROLL':
        direction = params.get('direction', 'down')
        amount = int(params.get('amount', 500))
        if direction == 'down':
            driver.execute_script(f"window.scrollBy(0, {amount});")
        elif direction == 'up':
            driver.execute_script(f"window.scrollBy(0, -{amount});")
        elif direction == 'left':
            driver.execute_script(f"window.scrollBy(-{amount}, 0);")
        elif direction == 'right':
            driver.execute_script(f"window.scrollBy({amount}, 0);")
        action_desc = f"Magic Agent scrolled {direction} by {amount} pixels"

    elif cmd == 'CLICK':
        x = int(params.get('x', 0))
        y = int(params.get('y', 0))
        body = driver.find_element(By.TAG_NAME, "body")
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(body, x, y).click().perform()
        action_desc = f"Magic Agent clicked at ({x}, {y})"

    elif cmd == 'TYPE':
        text = params.get('text', '')
        actions = ActionChains(driver)
        actions.send_keys(text).perform()
        action_desc = f"Magic Agent typed: {text}"

    elif cmd == 'PRESS_KEY':
        key = params.get('key', '').upper()
        if hasattr(Keys, key):
            actions = ActionChains(driver)
            actions.send_keys(getattr(Keys, key)).perform()
        action_desc = f"Magic Agent pressed key: {key}"

    elif cmd == 'PRESS_SHORTCUT':
        keys_str = params.get('keys', '')
        key_list = keys_str.split('+')
        actions = ActionChains(driver)
        for k in key_list[:-1]:
            actions.key_down(getattr(Keys, k.upper()))
        actions.send_keys(key_list[-1].lower() if len(key_list[-1]) == 1 else getattr(Keys, key_list[-1].upper()))
        for k in reversed(key_list[:-1]):
            actions.key_up(getattr(Keys, k.upper()))
        actions.perform()
        action_desc = f"Magic Agent pressed shortcut: {keys_str}"

    elif cmd == 'END_BROWSER':
        close_browser(phone)
        action_desc = "Magic Agent ended browser session"
        return action_desc  # No screenshot after end

    elif cmd == 'ASK_USER':
        question = params.get('question', '')
        state['pending_question'] = question
        state['mode'] = 'asking'
        send_whatsapp_message(phone, question)
        action_desc = f"Magic Agent is asking: {question}"
        return action_desc  # Exit loop

    time.sleep(1)  # Small delay for page to settle
    return action_desc

def upload_media(image_path):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {"file": ("screenshot.png", open(image_path, "rb"), "image/png")}
    data = {"messaging_product": "whatsapp", "type": "image/png"}
    response = requests.post(url, headers=headers, files=files, data=data)
    if response.status_code == 200:
        return response.json().get('id')
    else:
        print(f"Failed to upload media: {response.text}")
        return None

def send_whatsapp_image(to_number: str, image_path: str, caption: str = ""):
    media_id = upload_media(image_path)
    if not media_id:
        send_whatsapp_message(to_number, "Error sending screenshot.")
        return

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {"id": media_id, "caption": caption},
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Failed to send image: {response.text}")

def send_whatsapp_message(to_number: str, message: str):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": message},
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Failed to send message: {response.text}")

def process_browser_loop(phone):
    state = get_user_state(phone)
    driver = state['browser']

    while state['mode'] == 'browsing':
        screenshot_base64 = take_screenshot(driver)
        w, h = state['viewport']['width'], state['viewport']['height']
        prompt = f"Current screenshot attached. Viewport: {w}x{h}. What action to take next? Respond with exactly one command."

        response = call_gemini(phone, prompt, screenshot_base64, is_browser_mode=True)

        cmd, params = parse_command(response)
        if not cmd:
            send_whatsapp_message(phone, "Magic Agent encountered an error in command.")
            close_browser(phone)
            break

        action_desc = execute_command(phone, cmd.upper(), params)

        # Send update to user
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            save_screenshot(driver, tmp.name)
            send_whatsapp_image(phone, tmp.name, action_desc)
        os.unlink(tmp.name)

        if cmd.upper() in ['END_BROWSER', 'ASK_USER']:
            break

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return Response(challenge, status=200)
        else:
            return Response(status=403)

    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2))

        try:
            if (body.get("entry") and
                body["entry"][0].get("changes") and
                body["entry"][0]["changes"][0].get("value") and
                body["entry"][0]["changes"][0]["value"].get("messages")):
                
                message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
                message_type = message_info.get("type")
                from_number = message_info.get("from")
                
                state = get_user_state(from_number)
                
                if message_type == "text":
                    user_message_text = message_info["text"]["body"]
                    print(f"Text message from {from_number}: {user_message_text}")
                    
                    if state['mode'] == 'asking':
                        # Handle answer
                        answer_prompt = f"User answered your question '{state['pending_question']}': {user_message_text}"
                        call_gemini(from_number, answer_prompt)  # Append to history
                        state['pending_question'] = None
                        state['mode'] = 'browsing'
                        # Continue loop
                        process_browser_loop(from_number)
                    else:
                        # Normal message or start
                        gemini_response = call_gemini(from_number, user_message_text)
                        
                        # Check for START_BROWSER
                        cmd, params = parse_command(gemini_response)
                        if cmd and cmd.upper() == 'START_BROWSER':
                            url = params.get('url')
                            driver = start_browser(from_number, url)
                            # Send initial screenshot
                            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                                save_screenshot(driver, tmp.name)
                                send_whatsapp_image(from_number, tmp.name, "Magic Agent started browser session.")
                            os.unlink(tmp.name)
                            # Start loop
                            process_browser_loop(from_number)
                            # After loop, send any final response if needed
                            send_whatsapp_message(from_number, gemini_response.replace(f"[{cmd} { ' '.join([f'{k}=\"{v}\"' for k,v in params.items()])}]", "").strip() or "Browser session ended.")
                        else:
                            send_whatsapp_message(from_number, gemini_response)
                
                else:
                    non_text_message = "Sorry, I only understand text messages for now."
                    print(f"Non-text message ({message_type}) from {from_number}.")
                    send_whatsapp_message(from_number, non_text_message)

        except (KeyError, IndexError, TypeError) as e:
            print(f"Error processing webhook: {e}")
            pass

        return Response(status=200)

if __name__ == '__main__':
    print("WhatsApp Bot Server started at http://localhost:5000")
    print("Waiting for webhook messages...")
    app.run(port=5000, debug=False)
