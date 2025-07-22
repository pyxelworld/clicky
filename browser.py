import os
import json
import requests
import time
import io
import traceback
import base64
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
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- AI MODEL CONFIGURATION ---
# Using gemini-1.5-flash as a stable, available vision model.
# If you have confirmed access to 'gemini-2.0-flash', you can change it back here.
AI_MODEL_NAME = "gemini-1.5-flash"

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)

user_sessions = {}

# --- SYSTEM PROMPT FOR MAGIC AGENT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a highly intelligent AI assistant with the ability to control a web browser to help users. You operate in two modes: CHAT and BROWSER. Your responses MUST ALWAYS be in a JSON format.

**JSON Response Structure:**
{
  "command": "COMMAND_NAME",
  "params": { ... },
  "thought": "Your reasoning for choosing this command.",
  "speak": "A short, user-friendly message describing your action. (e.g., 'Okay, searching for that now.')"
}

--- AVAILABLE COMMANDS ---

1.  **Start Browser Session:**
    - Description: Initiates the browser when a user's request requires web access.
    - `command`: "START_BROWSER"
    - `params`: {}
    - Example: `{"command": "START_BROWSER", "params": {}, "thought": "The user wants me to find information online, so I need to start the browser.", "speak": "Alright, let me open the browser to look that up for you."}`

2.  **Type Text:**
    - Description: Types text into a field. You MUST specify the coordinates (x, y) of the element to type into. Analyze the screenshot with its grid to find the coordinates.
    - `command`: "TYPE"
    - `params`: {"x": <int>, "y": <int>, "text": "<text_to_type>", "enter": <true/false>}
    - Example: `{"command": "TYPE", "params": {"x": 500, "y": 350, "text": "best restaurants in Paris", "enter": true}, "thought": "I need to type the search query into the search bar located at these coordinates and press Enter.", "speak": "Typing 'best restaurants in Paris' into the search bar."}`

3.  **Click Element:**
    - Description: Clicks on an element at the specified (x, y) coordinates.
    - `command`: "CLICK"
    - `params`: {"x": <int>, "y": <int>}
    - Example: `{"command": "CLICK", "params": {"x": 800, "y": 355}, "thought": "I need to click the search button to submit the query.", "speak": "Clicking the search button."}`

4.  **Scroll Page:**
    - Description: Scrolls the page 'up' or 'down'.
    - `command`: "SCROLL"
    - `params`: {"direction": "<up|down>"}
    - Example: `{"command": "SCROLL", "params": {"direction": "down"}, "thought": "I need to see more content on the page.", "speak": "Scrolling down to see more..."}`

5.  **End Browser Session:**
    - Description: Closes the browser and summarizes the findings. Use this when the task is complete.
    - `command`: "END_BROWSER"
    - `params`: {"reason": "<summary_of_findings_or_answer>"}
    - Example: `{"command": "END_BROWSER", "params": {"reason": "I found that the best-rated restaurant is 'Le Cinq'. It has a 5-star rating and is known for its French cuisine."}, "thought": "I have found the information. I will close the browser and report back.", "speak": "Okay, I've finished the task and found the answer."}`

6.  **Ask User for Information:**
    - Description: Pauses the browser session to ask the user for clarification.
    - `command`: "PAUSE_AND_ASK"
    - `params`: {"question": "What should I do next?"}
    - Example: `{"command": "PAUSE_AND_ASK", "params": {"question": "I see a login form. Should I use the credentials you provided earlier?"}, "thought": "The page is ambiguous. I need clarification from the user.", "speak": "I need a little more information from you."}`

7.  **Answer Directly (Chat Mode):**
    - Description: If the browser is not needed, you can just talk to the user.
    - `command`: "SPEAK"
    - `params`: {"text": "Your response to the user."}
    - Example: `{"command": "SPEAK", "params": {"text": "Hello! I'm Magic Agent. How can I help you today?"}, "thought": "This is a simple greeting, no browser needed.", "speak": "Hello! I'm Magic Agent. How can I help you today?"}`

You are in BROWSER mode when a browser is open. You will receive a screenshot and must respond with a browser action command (`TYPE`, `CLICK`, `SCROLL`). When the task is done, use `END_BROWSER`. If you are in CHAT mode, you can either `START_BROWSER` or `SPEAK`.
"""

# Configure the Gemini client
genai.configure(api_key=GEMINI_API_KEY)

# --- WHATSAPP HELPER FUNCTIONS ---

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
    """Uploads an image via the Graph API and sends it to the user."""
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {
        'file': (image_path.name, open(image_path, 'rb'), 'image/png'),
        'messaging_product': (None, 'whatsapp'),
        'type': (None, 'image/png')
    }
    media_id = None
    try:
        response = requests.post(upload_url, headers=headers, files=files)
        response.raise_for_status()
        media_id = response.json().get('id')
    except requests.exceptions.RequestException as e:
        print(f"Error uploading WhatsApp media: {e} - {response.text}")
        send_whatsapp_message(to, "Sorry, I had trouble generating the browser view. Let's try that again.")
        return

    if not media_id:
        print("Failed to get media ID from WhatsApp upload.")
        send_whatsapp_message(to, "Sorry, I couldn't process the browser image.")
        return

    send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
    try:
        response = requests.post(send_url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Sent image message to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp image message: {e} - {response.text}")

# --- BROWSER AUTOMATION FUNCTIONS ---

def get_or_create_session(phone_number):
    """Retrieves or initializes a new session for a given phone number."""
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "mode": "CHAT",
            "driver": None,
            "chat_history": [],
            "original_prompt": "",
            "user_dir": user_dir,
            "downloads_dir": user_dir / "downloads",
            "profile_dir": user_dir / "profile",
        }
        session["downloads_dir"].mkdir(parents=True, exist_ok=True)
        session["profile_dir"].mkdir(parents=True, exist_ok=True)
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
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        traceback.print_exc()
        return None

def close_browser(session):
    """Closes the Selenium browser and resets session state."""
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try:
            session["driver"].quit()
        except Exception as e:
            print(f"Error while quitting browser: {e}")
        finally:
            session["driver"] = None
    session["mode"] = "CHAT"
    session["original_prompt"] = ""

def take_screenshot_with_grid(driver, session, grid_interval=100):
    """Takes a screenshot and overlays a coordinate grid."""
    screenshot_path = session["user_dir"] / f"screenshot_{int(time.time())}.png"
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)
        width, height = image.size
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", size=12)
        except IOError:
            print("DejaVuSans.ttf font not found. Using default font.")
            font = ImageFont.load_default()

        for x in range(0, width, grid_interval):
            draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 128), width=1)
            draw.text((x + 2, 2), str(x), fill="red", font=font)
        for y in range(0, height, grid_interval):
            draw.line([(0, y), (width, y)], fill=(255, 0, 0, 128), width=1)
            draw.text((2, y + 2), str(y), fill="red", font=font)

        image.save(screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        traceback.print_exc()
        return None

# --- AI & LOGIC FUNCTIONS ---

def call_ai(chat_history, image_path=None):
    """
    Calls the Gemini AI model. It can handle both text-only and multi-modal (text+image) requests.
    """
    model = genai.GenerativeModel(
        AI_MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        generation_config={"response_mime_type": "application/json"}
    )
    
    chat = model.start_chat(history=chat_history)
    
    last_user_message_content = chat_history[-1]['parts'] if chat_history and chat_history[-1]['role'] == 'user' else [""]
    prompt_parts = list(last_user_message_content)

    if image_path:
        print(f"AI Call: Vision mode with image {image_path.name}")
        try:
            img_part = {"mime_type": "image/png", "data": image_path.read_bytes()}
            prompt_parts.append(img_part)
        except Exception as e:
            print(f"Error reading image file for AI: {e}")
            return json.dumps({
                "command": "END_BROWSER",
                "params": {"reason": f"An internal error occurred trying to read the screen image. Error: {e}"},
                "thought": "The image file could not be read. I must end the session.",
                "speak": "I've run into an unexpected error with the screen view and need to stop."
            })
    else:
        print("AI Call: Chat mode")

    try:
        response = chat.send_message(prompt_parts)
        return response.text
    except Exception as e:
        print(f"CRITICAL: Error calling Gemini API: {e}")
        traceback.print_exc()
        return json.dumps({
            "command": "END_BROWSER",
            "params": {"reason": f"An internal error occurred with the AI model: {e}"},
            "thought": "The AI API call failed. I must end the session to be safe.",
            "speak": "I've run into an unexpected error and have to stop this browser session."
        })

def process_ai_command(from_number, ai_response_text):
    """Parses AI response and executes the corresponding action."""
    session = get_or_create_session(from_number)
    try:
        print(f"AI Response: {ai_response_text}")
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        print("AI returned non-JSON response. Treating as a simple text reply.")
        send_whatsapp_message(from_number, ai_response_text)
        session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
        if session["mode"] == "BROWSER":
             send_whatsapp_message(from_number, "I seem to be having trouble with my internal commands. I'll close the browser for now.")
             close_browser(session)
        return

    command = command_data.get("command")
    params = command_data.get("params", {})
    thought = command_data.get("thought", "No thought provided.")
    speak = command_data.get("speak", "")

    print(f"Executing command: {command} with params: {params}")
    print(f"AI Thought: {thought}")

    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})

    if speak:
        send_whatsapp_message(from_number, speak)

    if command == "START_BROWSER":
        driver = start_browser(session)
        if not driver:
            send_whatsapp_message(from_number, "Sorry, I encountered an error and couldn't open the browser. Please try again.")
            close_browser(session)
            return

        time.sleep(2)
        screenshot_path = take_screenshot_with_grid(driver, session)
        if screenshot_path:
            caption = "Okay, the browser is open. Here is the starting page. What should I do first?"
            send_whatsapp_image(from_number, screenshot_path, caption=caption)
            ai_response = call_ai(session["chat_history"], image_path=screenshot_path)
            process_ai_command(from_number, ai_response)
        else:
            send_whatsapp_message(from_number, "I started the browser but couldn't get a view of the page.")
            close_browser(session)

    elif command in ["TYPE", "CLICK", "SCROLL"] and session["mode"] == "BROWSER":
        driver = session.get("driver")
        if not driver:
            send_whatsapp_message(from_number, "My browser connection was lost. Please start the task again.")
            close_browser(session)
            return

        try:
            if command == "TYPE":
                x, y, text_to_type = params['x'], params['y'], params['text']
                element = driver.find_element(By.TAG_NAME, 'body')
                action = ActionChains(driver).move_to_element_with_offset(element, x, y).click()
                action.send_keys(text_to_type)
                if params.get("enter", False):
                    action.send_keys(u'\ue007')
                action.perform()

            elif command == "CLICK":
                x, y = params['x'], params['y']
                element = driver.find_element(By.TAG_NAME, 'body')
                ActionChains(driver).move_to_element_with_offset(element, x, y).click().perform()

            elif command == "SCROLL":
                direction = params.get('direction', 'down')
                scroll_amount = 500 if direction == 'down' else -500
                driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            
            time.sleep(2)
            screenshot_path = take_screenshot_with_grid(driver, session)
            if screenshot_path:
                send_whatsapp_image(from_number, screenshot_path, caption=f"Action done: {speak}")
                ai_response = call_ai(session["chat_history"], image_path=screenshot_path)
                process_ai_command(from_number, ai_response)
            else:
                 send_whatsapp_message(from_number, "I performed the action, but couldn't get a new view of the page.")
                 close_browser(session)

        except Exception as e:
            print(f"Error during browser action: {e}")
            send_whatsapp_message(from_number, f"I tried to perform an action but ran into an error: {e}. I'll close the browser for safety.")
            close_browser(session)

    elif command == "PAUSE_AND_ASK":
        question = params.get("question", "I need some more information.")
        send_whatsapp_message(from_number, question)

    elif command == "END_BROWSER":
        reason = params.get("reason", "Task completed successfully.")
        send_whatsapp_message(from_number, f"*Summary from Magic Agent:*\n{reason}")
        close_browser(session)

    elif command == "SPEAK":
        pass

    else:
        print(f"Unknown command received: {command}")
        send_whatsapp_message(from_number, "I received an unknown command from my brain. Resetting.")
        if session["mode"] == "BROWSER":
            close_browser(session)

# --- FLASK WEBHOOK ---

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            print("Webhook verification successful!")
            return Response(request.args.get('hub.challenge'), status=200)
        print("Webhook verification failed.")
        return Response('Verification token mismatch', status=403)

    if request.method == 'POST':
        body = request.get_json()

        try:
            # CORRECTED SECTION: The faulty 'if' check is removed.
            # We now rely solely on the try/except block to filter for valid messages.
            # This is more robust and correctly handles various webhook event types.

            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "I can only process text messages right now. Please send me your request as text.")
                return Response(status=200)

            from_number = message_info["from"]
            user_message_text = message_info["text"]["body"]
            print(f"Received message from {from_number}: '{user_message_text}'")
            
            session = get_or_create_session(from_number)
            
            session["chat_history"].append({"role": "user", "parts": [user_message_text]})

            if session["mode"] == "CHAT":
                session["original_prompt"] = user_message_text
                ai_response = call_ai(session["chat_history"])
                process_ai_command(from_number, ai_response)

            elif session["mode"] == "BROWSER":
                driver = session.get("driver")
                if not driver:
                     send_whatsapp_message(from_number, "It seems my browser closed unexpectedly. Let's start over.")
                     close_browser(session)
                     session["original_prompt"] = user_message_text
                     ai_response = call_ai(session["chat_history"])
                     process_ai_command(from_number, ai_response)
                     return Response(status=200)

                send_whatsapp_message(from_number, "Thanks for the info! Let me continue with that...")
                screenshot_path = take_screenshot_with_grid(driver, session)
                if screenshot_path:
                    send_whatsapp_image(from_number, screenshot_path, caption="Okay, looking at the page again with your new instructions.")
                    ai_response = call_ai(session["chat_history"], image_path=screenshot_path)
                    process_ai_command(from_number, ai_response)
                else:
                    send_whatsapp_message(from_number, "I couldn't get a view of the page to continue. Closing browser.")
                    close_browser(session)
        
        except (KeyError, IndexError, TypeError):
            # This block will now correctly catch any webhook event that is NOT a user message
            # (e.g., status updates, etc.), and silently ignore them.
            pass
        except Exception as e:
            print(f"Error processing webhook POST request: {e}")
            traceback.print_exc()

        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    print(f"Listening on port 5000. Webhook URL: [YOUR_TUNNEL_URL]/webhook")
    print("Ensure your Cloudflared or ngrok tunnel is running and pointed to port 5000.")
    # In the original error, the app was named 'browser', let's name it correctly.
    app.name = 'whatsapp'
    app.run(port=5000, debug=False)
