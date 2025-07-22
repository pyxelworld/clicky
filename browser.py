import os
import json
import requests
import base64
import io
import time

from flask import Flask, request, Response
from google import genai
from google.genai import types

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- AI & BROWSER CONFIGURATION ---
# IMPORTANT: YOU MUST USE gemini-1.5-flash FOR VISION CAPABILITIES. 
# The model you requested, gemini-2.0-flash, does not currently support vision (image inputs).
# I am using gemini-1.5-flash as it is required for this feature to work.
AI_MODEL_NAME = "gemini-1.5-flash" 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- SYSTEM PROMPTS ---
SYSTEM_PROMPT_CHAT = [
    types.Part.from_text("""You are Magic Agent, a helpful AI assistant integrated into WhatsApp. 
Your goal is to assist users with their requests.
You have a special ability: you can browse the internet to perform tasks.
If the user asks you to do something that requires a browser (e.g., 'find a recipe', 'book a flight', 'check the news'), you must respond ONLY with the following JSON command to start a browser session:
{"command": "BROWSE", "url": "https://www.google.com/search?q=THEIR_SEARCH_QUERY"}
Replace THEIR_SEARCH_QUERY with what the user wants to search for. For a generic request like "open the browser", you can use "https://www.google.com".
For all other conversational messages, just chat normally and be friendly.""")
]

SYSTEM_PROMPT_BROWSE = [
    types.Part.from_text("""You are Magic Agent, an AI with control over a web browser.
You are in a browser session. You will receive a screenshot of the current page. The screenshot has numbered labels on all interactive elements (links, buttons, input fields).
Your task is to analyze the screenshot and the user's request to decide the next single action to take.
You must respond ONLY with a single JSON object describing your action. No other text or explanation.

Here are your available commands:

1.  **CLICK**: Clicks an element.
    {"command": "CLICK", "element_id": <number>, "reason": "Clicking the 'Login' button."}

2.  **TYPE**: Types text into an input field and can optionally press Enter.
    {"command": "TYPE", "element_id": <number>, "text": "text to type", "press_enter": <true_or_false>, "reason": "Typing username into the field."}

3.  **SCROLL**: Scrolls the page up or down.
    {"command": "SCROLL", "direction": "<up_or_down>", "reason": "Scrolling down to see more products."}
    
4.  **NAVIGATE**: Go to a new URL.
    {"command": "NAVIGATE", "url": "https://www.example.com", "reason": "Navigating to the homepage."}

5.  **ASK_USER**: If you need more information from the user to proceed.
    {"command": "ASK_USER", "question": "What is your destination city?", "reason": "Asking for clarification."}

6.  **END_BROWSE**: When the task is fully complete and you are finished with the browser.
    {"command": "END_BROWSE", "reason": "The flight is booked, task complete."}

**Workflow:**
1.  Observe the screenshot.
2.  Read the user's instructions.
3.  Choose ONE single command from the list above.
4.  Provide the command as a JSON object. The 'reason' field is mandatory and should be a short sentence explaining your action for the user.

Example: If the user says "Search for cats" and the screenshot is Google's homepage with the search bar labeled '7'.
Your response: {"command": "TYPE", "element_id": 7, "text": "cats", "press_enter": true, "reason": "Searching for cats on Google."}
""")
]


# --- GLOBAL STATE MANAGEMENT ---
# Stores session data per phone number
user_sessions = {}

# --- FLASK APP ---
app = Flask(__name__)

# --- HELPER FUNCTIONS ---

def setup_user_directories(phone_number):
    """Creates dedicated profile and download directories for a user."""
    user_dir = os.path.join(BASE_DIR, 'user_data', phone_number)
    profile_dir = os.path.join(user_dir, 'chrome_profile')
    download_dir = os.path.join(user_dir, 'downloads')
    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)
    return profile_dir, download_dir

def get_session(phone_number):
    """Retrieves or creates a user session."""
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        profile_dir, download_dir = setup_user_directories(phone_number)
        user_sessions[phone_number] = {
            "mode": "chat",  # 'chat' or 'browsing'
            "driver": None,
            "profile_dir": profile_dir,
            "download_dir": download_dir,
            "history": [],
            "elements_map": {}
        }
    return user_sessions[phone_number]

# --- WHATSAPP MESSAGING ---

def send_whatsapp_message(to_number, message):
    """Sends a text message to a WhatsApp number."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": message}}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Message sent to {to_number} successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message: {e} - {response.text}")

def upload_media_for_whatsapp(image_path):
    """Uploads an image to Meta's servers and returns the media ID."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {
        'file': (os.path.basename(image_path), open(image_path, 'rb'), 'image/png'),
        'messaging_product': (None, 'whatsapp')
    }
    try:
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        media_id = response.json().get("id")
        print(f"Media uploaded successfully. ID: {media_id}")
        return media_id
    except requests.exceptions.RequestException as e:
        print(f"Failed to upload media: {e} - {response.text}")
        return None

def send_whatsapp_image(to_number, image_path, caption=""):
    """Sends an image with a caption to a WhatsApp number."""
    media_id = upload_media_for_whatsapp(image_path)
    if not media_id:
        send_whatsapp_message(to_number, f"Sorry, I couldn't generate the screenshot, but here's the update:\n\n{caption}")
        return

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {
            "id": media_id,
            "caption": caption
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Image message sent to {to_number} successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send image message: {e} - {response.text}")

# --- BROWSER AUTOMATION ---

def start_browser(session):
    """Starts a Selenium WebDriver instance for the user."""
    if session.get("driver"):
        print("Browser already running for this session.")
        return session["driver"]
    
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1024")
    options.add_argument(f"user-data-dir={session['profile_dir']}") # Profile per number
    
    # Setup download preferences
    prefs = {"download.default_directory": session['download_dir']}
    options.add_experimental_option("prefs", prefs)
    
    # Using chromedriver from PATH. Ensure it's installed and in your PATH.
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver
        return driver
    except Exception as e:
        print(f"Error starting browser: {e}")
        return None

def take_and_annotate_screenshot(driver, session):
    """Takes a screenshot, finds interactive elements, and annotates the image."""
    print("Taking and annotating screenshot...")
    # Find interactive elements
    js_script = """
    var elements = Array.from(document.querySelectorAll('a, button, input, textarea, select, [role="button"], [role="link"]'));
    var visibleElements = [];
    elements.forEach(function(el, i) {
        var rect = el.getBoundingClientRect();
        var style = window.getComputedStyle(el);
        if (rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && el.getAttribute('aria-hidden') !== 'true') {
            visibleElements.push({
                'id': i,
                'x': rect.left,
                'y': rect.top,
                'width': rect.width,
                'height': rect.height
            });
        }
    });
    return visibleElements;
    """
    
    interactive_elements = driver.execute_script(js_script)
    all_elements = driver.find_elements(By.CSS_SELECTOR, 'a, button, input, textarea, select, [role="button"], [role="link"]')
    
    elements_map = {el_data['id']: all_elements[el_data['id']] for el_data in interactive_elements}
    session["elements_map"] = elements_map
    
    # Take screenshot
    screenshot_bytes = driver.get_screenshot_as_png()
    image = Image.open(io.BytesIO(screenshot_bytes))
    draw = ImageDraw.Draw(image)

    # Use a basic font. On some systems you might need to specify a path e.g., "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        print("Arial font not found, using default font.")
        font = ImageFont.load_default()

    # Draw labels
    element_counter = 1
    for el_data in interactive_elements:
        x, y, w, h = el_data['x'], el_data['y'], el_data['width'], el_data['height']
        if x > 0 and y > 0:
            # Draw box
            draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
            # Draw label
            label = str(element_counter)
            draw.text((x + 2, y + 2), label, fill="white", font=font, stroke_width=2, stroke_fill="black")
            # Update map with the counter ID
            original_id = el_data['id']
            session["elements_map"][element_counter] = session["elements_map"].pop(original_id)
            element_counter += 1

    annotated_image_path = os.path.join(session["profile_dir"], "annotated_screenshot.png")
    image.save(annotated_image_path)
    
    # Convert to base64 for Gemini
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    return annotated_image_path, image_base64


# --- AI & COMMAND PROCESSING ---

def get_ai_response(session, user_message, image_base64=None):
    """Calls Gemini API with appropriate context and returns the response."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        system_instruction = SYSTEM_PROMPT_BROWSE if session["mode"] == "browsing" else SYSTEM_PROMPT_CHAT
        
        # Build content payload
        contents = session["history"] + [types.Content(role="user", parts=[types.Part.from_text(text=user_message)])]
        
        if image_base64:
            image_part = types.Part(
                inline_data=types.Blob(
                    mime_type='image/png',
                    data=base64.b64decode(image_base64)
                )
            )
            # Add image to the last user message
            contents[-1].parts.insert(0, image_part)
        
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain" if session["mode"] == "chat" else "application/json",
            system_instruction=system_instruction
        )
        
        response = client.models.get_model(AI_MODEL_NAME).generate_content(
            contents=contents,
            config=generate_content_config,
        )
        
        ai_response_text = response.text.strip()
        print(f"AI Response: {ai_response_text}")

        # Update history
        session["history"].append(contents[-1]) # Add user part
        session["history"].append(response.candidates[0].content) # Add model part
        # Limit history size to prevent overly large payloads
        session["history"] = session["history"][-10:]

        return ai_response_text

    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return '{"command": "ASK_USER", "question": "I encountered an error. Can you please clarify or try a different approach?", "reason": "Recovering from an internal error."}' if session["mode"] == "browsing" else "Sorry, I had trouble processing that. Please try again."


def process_command(phone_number, command_json):
    """Executes the command from the AI."""
    session = get_session(phone_number)
    driver = session["driver"]
    
    try:
        command_data = json.loads(command_json)
        command = command_data.get("command")
        reason = command_data.get("reason", "Performing an action.")
        caption = f"Magic Agent: {reason}"

        if command == "CLICK":
            element_id = command_data.get("element_id")
            element = session["elements_map"].get(element_id)
            if element:
                element.click()
                time.sleep(2) # Wait for page to potentially load
                handle_browsing_interaction(phone_number, "Clicked the element. What's next?")
            else:
                send_whatsapp_message(phone_number, f"Magic Agent tried to click, but couldn't find element {element_id}. Please check the screenshot and advise.")

        elif command == "TYPE":
            element_id = command_data.get("element_id")
            text_to_type = command_data.get("text")
            press_enter = command_data.get("press_enter", False)
            element = session["elements_map"].get(element_id)
            if element:
                element.click()
                time.sleep(0.5)
                element.send_keys(text_to_type)
                if press_enter:
                    element.send_keys(Keys.RETURN)
                time.sleep(2)
                handle_browsing_interaction(phone_number, f"Typed '{text_to_type}'. What's next?")
            else:
                send_whatsapp_message(phone_number, f"Magic Agent tried to type, but couldn't find element {element_id}. Please check the screenshot and advise.")
        
        elif command == "SCROLL":
            direction = command_data.get("direction")
            if direction == "down":
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
            elif direction == "up":
                driver.execute_script("window.scrollBy(0, -window.innerHeight);")
            time.sleep(1)
            handle_browsing_interaction(phone_number, "Scrolled the page. What's next?")

        elif command == "NAVIGATE":
            url = command_data.get("url")
            driver.get(url)
            time.sleep(2)
            handle_browsing_interaction(phone_number, f"Navigated to {url}. What's next?")
        
        elif command == "ASK_USER":
            question = command_data.get("question")
            send_whatsapp_message(phone_number, f"Magic Agent has a question for you: {question}")
            # We wait for the user's next message, no further action needed here.
            
        elif command == "END_BROWSE":
            send_whatsapp_message(phone_number, caption)
            if driver:
                driver.quit()
            session["driver"] = None
            session["mode"] = "chat"
            session["history"] = [] # Clear history for a fresh start
            print(f"Browser session ended for {phone_number}.")

        else:
            send_whatsapp_message(phone_number, "Magic Agent sent an unknown command. Please try again.")

    except json.JSONDecodeError:
        send_whatsapp_message(phone_number, f"Magic Agent got confused and sent an invalid response. Let's try that again. What would you like to do on the current page?")
        # Resend the last state to the user to get them back on track
        annotated_image_path, _ = take_and_annotate_screenshot(driver, session)
        send_whatsapp_image(phone_number, annotated_image_path, "This is the current screen.")
    except Exception as e:
        print(f"Error processing command: {e}")
        send_whatsapp_message(phone_number, "An unexpected error occurred while performing the action. Please try again.")
        session["mode"] = "chat"
        if session.get("driver"):
            session["driver"].quit()
            session["driver"] = None


def handle_browsing_interaction(phone_number, user_message):
    """The main loop for a browsing session interaction."""
    session = get_session(phone_number)
    driver = session["driver"]
    if not driver:
        send_whatsapp_message(phone_number, "Error: Browser is not running. Ending session.")
        session["mode"] = "chat"
        return
        
    # 1. Take screenshot of current state
    annotated_image_path, image_base64 = take_and_annotate_screenshot(driver, session)
    
    # 2. Inform user we're thinking (good for long AI calls)
    # send_whatsapp_message(phone_number, "Magic Agent is analyzing the page...")

    # 3. Get AI command
    ai_command_json = get_ai_response(session, user_message, image_base64)

    # 4. Update user on the action to be taken, based on the AI's "reason"
    try:
        reason = json.loads(ai_command_json).get("reason", "performing the next step.")
        caption = f"Magic Agent: {reason}"
        if json.loads(ai_command_json).get("command") not in ["ASK_USER", "END_BROWSE"]:
             send_whatsapp_image(phone_number, annotated_image_path, caption)
    except:
        # If JSON is invalid, we'll handle it in process_command
        pass
        
    # 5. Execute command
    process_command(phone_number, ai_command_json)


# --- FLASK WEBHOOK ---

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        else:
            return Response(status=403)

    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2))

        try:
            if (body.get("entry") and body["entry"][0].get("changes") and
                body["entry"][0]["changes"][0].get("value") and
                body["entry"][0]["changes"][0]["value"].get("messages")):
                
                message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
                from_number = message_info["from"]
                
                if message_info["type"] == "text":
                    user_message = message_info["text"]["body"]
                    session = get_session(from_number)

                    if session["mode"] == "chat":
                        ai_response = get_ai_response(session, user_message)
                        try:
                            command_data = json.loads(ai_response)
                            if command_data.get("command") == "BROWSE":
                                session["mode"] = "browsing"
                                send_whatsapp_message(from_number, "Magic Agent is starting the browser...")
                                driver = start_browser(session)
                                if driver:
                                    driver.get(command_data.get("url", "https://google.com"))
                                    time.sleep(2)
                                    handle_browsing_interaction(from_number, user_message)
                                else:
                                    send_whatsapp_message(from_number, "Sorry, I couldn't start the browser due to an internal error.")
                                    session["mode"] = "chat"
                            else:
                                # Not a browse command, just a weird JSON response
                                send_whatsapp_message(from_number, "I'm sorry, I'm not sure how to respond to that.")
                        except json.JSONDecodeError:
                            # It's a normal chat message
                            send_whatsapp_message(from_number, ai_response)
                            
                    elif session["mode"] == "browsing":
                        handle_browsing_interaction(from_number, user_message)

                else:
                    send_whatsapp_message(message_info["from"], "Sorry, I only understand text messages.")

        except Exception as e:
            print(f"Error processing webhook: {e}")
            import traceback
            traceback.print_exc()

        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server ---")
    print("Ensuring user data directories exist...")
    os.makedirs(os.path.join(BASE_DIR, 'user_data'), exist_ok=True)
    print("Server starting on http://localhost:5000")
    print("Waiting for messages via webhook...")
    app.run(port=5000, debug=False)
