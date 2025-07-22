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
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}

# --- SYSTEM PROMPT (UNCHANGED) ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly intelligent AI assistant with the ability to control a web browser to help users. You operate in two modes: CHAT and BROWSER. Your responses MUST be in a JSON format.
... [The rest of the system prompt remains the same as before] ...
"""
# Note: For brevity, the full system prompt is omitted here but is identical to the previous version in the code below.

# --- FULL CODE WITH FIXES ---

SYSTEM_PROMPT = """
You are "Magic Agent," a highly intelligent AI assistant with the ability to control a web browser to help users.

You operate in two modes:
1.  **CHAT**: A standard conversational mode.
2.  **BROWSER**: A mode where you interact with a web browser to complete tasks.

**COMMANDS:**
Your responses MUST be in a JSON format. When you are in CHAT mode and decide you need to use the browser, you will issue the `START_BROWSER` command. Once in BROWSER mode, you will receive a screenshot of the web page and must respond with one of the available browser action commands.

**JSON Response Structure:**
{
  "command": "COMMAND_NAME",
  "params": { ... parameters for the command ... },
  "thought": "Your reasoning for choosing this command.",
  "speak": "A short, user-friendly message describing your action. (e.g., 'Okay, searching for that now.')"
}

--- AVAILABLE COMMANDS ---

1.  **Start Browser Session:**
    - Description: Initiates the browser to start a task. You should use this when the user's request requires web access.
    - `command`: "START_BROWSER"
    - `params`: {}
    - Example: `{"command": "START_BROWSER", "params": {}, "thought": "The user wants me to find information online, so I need to start the browser.", "speak": "Alright, let me open the browser to look that up for you."}`

2.  **Type Text:**
    - Description: Types text into a field. You must specify the coordinates (x, y) of the element you want to type into. The screenshot you receive will have a grid to help you.
    - `command`: "TYPE"
    - `params`: {"x": <int>, "y": <int>, "text": "<text_to_type>"}
    - Example: `{"command": "TYPE", "params": {"x": 500, "y": 350, "text": "best restaurants in Paris"}, "thought": "I need to type the search query into the search bar located at these coordinates.", "speak": "Typing 'best restaurants in Paris' into the search bar."}`

3.  **Click Element:**
    - Description: Clicks on a button, link, or any other element at the specified (x, y) coordinates.
    - `command`: "CLICK"
    - `params`: {"x": <int>, "y": <int>}
    - Example: `{"command": "CLICK", "params": {"x": 800, "y": 355}, "thought": "I need to click the search button to submit the query.", "speak": "Clicking the search button."}`

4.  **Scroll Page:**
    - Description: Scrolls the page up or down.
    - `command`: "SCROLL"
    - `params`: {"direction": "<up|down>"}
    - Example: `{"command": "SCROLL", "params": {"direction": "down"}, "thought": "I need to see more content on the page.", "speak": "Scrolling down to see more..."}`

5.  **End Browser Session:**
    - Description: Closes the browser and summarizes the findings or answers the user's question. Use this when the task is complete.
    - `command`: "END_BROWSER"
    - `params`: {"reason": "<summary_of_findings_or_answer>"}
    - Example: `{"command": "END_BROWSER", "params": {"reason": "I found that the best-rated restaurant is 'Le Cinq'. It has a 5-star rating and is known for its French cuisine."}, "thought": "I have successfully found the information the user requested. I will now close the browser and provide the answer.", "speak": "Okay, I've finished the task."}`

6.  **Ask User for Information:**
    - Description: If you are in a browser session and need more information from the user to proceed, use this command. The browser session will pause.
    - `command`: "PAUSE_AND_ASK"
    - `params`: {"question": "What should I do next? or a specific question"}
    - Example: `{"command": "PAUSE_AND_ASK", "params": {"question": "I've found several login buttons. Which one should I use?"}, "thought": "The page is ambiguous. I need clarification from the user before I can proceed.", "speak": "I need a little more information from you."}`
"""

# --- WHATSAPP HELPER FUNCTIONS (UNCHANGED) ---
def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp text message: {e}")

def send_whatsapp_image(to, image_path, caption=""):
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {'file': (image_path.name, open(image_path, 'rb'), 'image/png'), 'messaging_product': (None, 'whatsapp'), 'type': (None, 'image/png')}
    try:
        response = requests.post(upload_url, headers=headers, files=files); response.raise_for_status()
        media_id = response.json()['id']
    except requests.exceptions.RequestException as e:
        print(f"Error uploading WhatsApp media: {e} - {response.text}")
        send_whatsapp_message(to, "Sorry, I had trouble generating the browser view.")
        return
    send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
    try:
        response = requests.post(send_url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}, json=data)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp image message: {e} - {response.text}")


# --- BROWSER & SESSION FUNCTIONS ---
def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        user_dir = USER_DATA_DIR / phone_number
        user_sessions[phone_number] = {
            "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "downloads_dir": user_dir / "downloads", "profile_dir": user_dir / "profile",
        }
        user_sessions[phone_number]["downloads_dir"].mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number]["profile_dir"].mkdir(parents=True, exist_ok=True)
    return user_sessions[phone_number]

def reset_session(session):
    if session.get("driver"):
        try:
            session["driver"].quit()
        except Exception: pass
    session["mode"] = "CHAT"
    session["driver"] = None
    session["chat_history"] = []
    session["original_prompt"] = ""
    print(f"Session reset for {session['user_dir'].name}")

def start_browser(session):
    if session.get("driver"): return session["driver"]
    options = Options()
    options.add_argument("--headless=new"); options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage"); options.add_argument("--window-size=1280,800")
    options.add_argument(f"--user-data-dir={session['profile_dir']}")
    prefs = {"download.default_directory": str(session['downloads_dir'])}
    options.add_experimental_option("prefs", prefs)
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver; return driver
    except Exception as e:
        print(f"Error starting browser: {e}"); return None

def close_browser(session):
    reset_session(session) # Closing is the same as a full reset

def take_screenshot_with_grid(driver, session, grid_interval=50): # *** FIX: Grid interval now 50px
    screenshot_path = session["user_dir"] / f"screenshot_{int(time.time())}.png"
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        width, height = image.size
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=10) # Smaller font for finer grid
        except IOError: font = ImageFont.load_default()
        for x in range(0, width, grid_interval):
            draw.line([(x, 0), (x, height)], fill="rgba(255,0,0,128)", width=1)
            if x > 0: draw.text((x + 2, 2), str(x), fill="red", font=font)
        for y in range(0, height, grid_interval):
            draw.line([(0, y), (width, y)], fill="rgba(255,0,0,128)", width=1)
            if y > 0: draw.text((2, y + 2), str(y), fill="red", font=font)
        image.save(screenshot_path)
        return screenshot_path
    except Exception as e:
        print(f"Error taking screenshot: {e}"); return None

# --- AI & LOGIC FUNCTIONS ---
def call_gemini_vision(prompt, image_path, chat_history):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # *** FIX: Use gemini-1.5-flash-latest, which is optimized for multimodal vision tasks. This is the key to fixing the error.
        model_name = "gemini-1.5-flash-latest"
        contents = []
        for entry in chat_history:
            role = 'user' if entry['role'] == 'user' else 'model'
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=entry['content'])]))
        image_part = types.Part.from_data(data=image_path.read_bytes(), mime_type='image/png')
        text_part = types.Part.from_text(f"User's main goal: {prompt}\nAnalyze the screenshot and decide the next single action. Respond with JSON.")
        contents.append(types.Content(role="user", parts=[text_part, image_part]))
        generate_content_config = types.GenerateContentConfig(response_mime_type="application/json", system_instruction=[types.Part.from_text(text=SYSTEM_PROMPT)])
        response_chunks = [chunk.text for chunk in client.models.generate_content_stream(model=model_name, contents=contents, config=generate_content_config)]
        return "".join(response_chunks)
    except Exception as e:
        print(f"Error calling Gemini Vision API: {e}")
        return json.dumps({"command": "END_BROWSER","params": {"reason": f"An internal error occurred with the AI Vision model: {e}"},"thought": "The AI vision API call failed.","speak": "I've run into an unexpected error and need to stop."})

def call_gemini_chat(chat_history):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # *** FIX: Using your preferred model for chat-only tasks.
        model_name = "gemini-2.0-flash" 
        contents = []
        for entry in chat_history:
            role = 'user' if entry['role'] == 'user' else 'model'
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=entry['content'])]))
        generate_content_config = types.GenerateContentConfig(response_mime_type="application/json", system_instruction=[types.Part.from_text(text=SYSTEM_PROMPT)])
        response_chunks = [chunk.text for chunk in client.models.generate_content_stream(model=model_name, contents=contents, config=generate_content_config)]
        return "".join(response_chunks)
    except Exception as e:
        print(f"Error calling Gemini Chat API: {e}")
        return json.dumps({"command": "SPEAK_ERROR", "params": {}, "thought": "Chat API failed.", "speak": "Sorry, I'm having trouble thinking. Please try again."})

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    try:
        command_data = json.loads(ai_response_text)
        command = command_data.get("command")
        params = command_data.get("params", {})
        thought = command_data.get("thought", "No thought provided.")
        speak = command_data.get("speak", "Okay, on it.")
        print(f"AI command: {command}, Params: {params}, Thought: {thought}")
        session["chat_history"].append({"role": "model", "content": ai_response_text})
        if command == "START_BROWSER":
            send_whatsapp_message(from_number, speak)
            session["mode"] = "BROWSER"
            driver = start_browser(session)
            if not driver: send_whatsapp_message(from_number, "Sorry, I couldn't start the browser."); close_browser(session); return
            time.sleep(1)
            screenshot_path = take_screenshot_with_grid(driver, session)
            if screenshot_path:
                send_whatsapp_image(from_number, screenshot_path, caption="Browser is open. I'll take the first step.")
                ai_response = call_gemini_vision(session["original_prompt"], screenshot_path, session["chat_history"])
                process_ai_command(from_number, ai_response)
        elif command in ["TYPE", "CLICK", "SCROLL"] and session["mode"] == "BROWSER":
            send_whatsapp_message(from_number, speak)
            driver = session["driver"]
            if not driver: send_whatsapp_message(from_number, "Browser session not found."); close_browser(session); return
            if command == "TYPE":
                x, y, text_to_type = params['x'], params['y'], params['text']
                ActionChains(driver).move_by_offset(x, y).click().send_keys(text_to_type).perform()
                ActionChains(driver).move_by_offset(-x, -y).perform()
            elif command == "CLICK":
                x, y = params['x'], params['y']
                ActionChains(driver).move_by_offset(x, y).click().perform()
                ActionChains(driver).move_by_offset(-x, -y).perform()
            elif command == "SCROLL":
                direction = params.get('direction', 'down')
                driver.execute_script(f"window.scrollBy(0, {600 if direction == 'down' else -600});")
            time.sleep(2)
            screenshot_path = take_screenshot_with_grid(driver, session)
            if screenshot_path:
                send_whatsapp_image(from_number, screenshot_path, caption=f"Action: {command}. {speak}")
                ai_response = call_gemini_vision(session["original_prompt"], screenshot_path, session["chat_history"])
                process_ai_command(from_number, ai_response)
        elif command == "PAUSE_AND_ASK":
            send_whatsapp_message(from_number, f"{speak}\n\n{params.get('question', 'What should I do?')}")
        elif command == "END_BROWSER":
            send_whatsapp_message(from_number, f"{speak}\n\n*Summary:*\n{params.get('reason', 'Task completed.')}")
            close_browser(session)
        else:
            send_whatsapp_message(from_number, speak)
    except json.JSONDecodeError:
        print(f"AI returned non-JSON: {ai_response_text}")
        send_whatsapp_message(from_number, ai_response_text if session["mode"] == "CHAT" else "I had a minor command issue. Let me try again.")
    except Exception as e:
        print(f"Error in process_ai_command: {e}"); traceback.print_exc()
        send_whatsapp_message(from_number, "A critical error occurred. Resetting session.")
        close_browser(session)

# --- FLASK WEBHOOK ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        return Response('Verification token mismatch', status=403)
    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2))
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            if message_info.get("type") != "text": return Response(status=200)
            from_number = message_info["from"]
            user_message_text = message_info["text"]["body"]
            session = get_or_create_session(from_number)
            # *** FIX: Add a reset command
            if user_message_text.strip().lower() in ['/novochat', '/reset']:
                reset_session(session)
                send_whatsapp_message(from_number, "Okay, let's start a new conversation!")
                return Response(status=200)
            session["chat_history"].append({"role": "user", "content": user_message_text})
            if session["mode"] == "CHAT":
                session["original_prompt"] = user_message_text
                ai_response = call_gemini_chat(session["chat_history"])
                process_ai_command(from_number, ai_response)
            elif session["mode"] == "BROWSER":
                send_whatsapp_message(from_number, "Thanks, I'll use that info to continue...")
                screenshot_path = take_screenshot_with_grid(session["driver"], session)
                if screenshot_path:
                    full_context = f"{session['original_prompt']}\nUser's latest instruction: {user_message_text}"
                    send_whatsapp_image(from_number, screenshot_path, caption="Okay, proceeding with your instructions.")
                    ai_response = call_gemini_vision(full_context, screenshot_path, session["chat_history"])
                    process_ai_command(from_number, ai_response)
        except (KeyError, IndexError, TypeError): pass
        except Exception as e: print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("Magic Agent WhatsApp Bot server starting...")
    app.run(port=5000, debug=False)
