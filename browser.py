import os
import json
import requests
import base64
import time
from flask import Flask, request, Response
from google import generativeai as genai
from google.genai import types
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image
from io import BytesIO

# --- Configuration ---
# Your API keys and tokens go here.
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Session and Browser Management ---
# This dictionary will hold the state for each user (phone number).
user_sessions = {}

def get_user_session(phone_number):
    """Retrieves or creates a session for a given phone number."""
    if phone_number not in user_sessions:
        user_sessions[phone_number] = {
            "browsing": False,
            "driver": None,
            "history": []
        }
    return user_sessions[phone_number]

def start_browser(phone_number):
    """Starts a new Selenium browser instance for a user."""
    session = get_user_session(phone_number)
    if session["browsing"]:
        return session["driver"]

    # Create a unique profile directory for each user to isolate sessions.
    profile_path = os.path.join(os.getcwd(), "profiles", phone_number)
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)

    chrome_options = Options()
    # Running in a terminal-only environment requires headless mode.
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-data-dir={profile_path}")
    chrome_options.add_argument("--window-size=1280,720") # Standard window size for consistent screenshots

    try:
        driver = webdriver.Chrome(options=chrome_options)
        session["browsing"] = True
        session["driver"] = driver
        return driver
    except Exception as e:
        print(f"Error starting ChromeDriver: {e}")
        return None


def close_browser(phone_number):
    """Closes the browser for a given user and cleans up the session."""
    session = get_user_session(phone_number)
    if session["browsing"] and session["driver"]:
        session["driver"].quit()
        session["browsing"] = False
        session["driver"] = None
        print(f"Browser session closed for {phone_number}.")

def take_screenshot(driver, phone_number):
    """Takes a screenshot of the current browser view."""
    # Create a directory for screenshots if it doesn't exist.
    screenshot_path = os.path.join(os.getcwd(), "screenshots")
    if not os.path.exists(screenshot_path):
        os.makedirs(screenshot_path)
    
    file_path = os.path.join(screenshot_path, f"{phone_number}.png")
    driver.save_screenshot(file_path)
    return file_path

# --- Gemini AI Interaction ---

def call_gemini_vision(prompt, image_path):
    """
    Calls the Gemini API with an image and a text prompt, using the genai.Client structure.
    This function is used when the bot is in browsing mode.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "gemini-1.5-flash" # This is a known multimodal model

        # The AI needs a detailed system prompt to know how to behave and what commands are available.
        system_prompt = """
        You are Magic Agent, an AI assistant with the ability to control a web browser.
        You will be given a prompt from a user and a screenshot of the current browser state.
        Your goal is to respond with a single JSON object containing a command to interact with the browser.

        Available commands:
        - {"command": "GOTO", "url": "https://www.google.com"} - Navigates to a specific URL.
        - {"command": "CLICK", "x": 350, "y": 500} - Clicks on a specific coordinate on the page.
        - {"command": "TYPE", "x": 350, "y": 500, "text": "Hello world"} - Clicks on a coordinate and types the given text.
        - {"command": "SCROLL", "direction": "DOWN"} - Scrolls the page. Valid directions are 'UP' or 'DOWN'.
        - {"command": "ASK_USER", "question": "What should I search for next?"} - Pauses to ask the user for more information.
        - {"command": "END_SESSION", "reason": "I have completed the requested task."} - Closes the browser and ends the session.

        Analyze the screenshot and the user's prompt carefully to determine the next best action.
        Be precise with your coordinates. The image resolution is 1280x720.
        Your response MUST be only the JSON command object and nothing else.
        """
        
        with open(image_path, "rb") as image_file:
            # The API requires the image to be in base64 format.
            image_data = base64.b64encode(image_file.read()).decode('utf-8')

        # The contents must include the user's text prompt and the image.
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_data(
                        mime_type="image/png",
                        data=base64.b64decode(image_data)
                    )
                ]
            )
        ]

        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text=system_prompt),
            ],
        )

        # Stream the response and join the chunks, as per your example.
        response_chunks = []
        for chunk in client.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=generate_content_config,
        ):
            response_chunks.append(chunk.text)
            
        return "".join(response_chunks)

    except Exception as e:
        print(f"Error calling Gemini Vision API: {e}")
        return '{"command": "ASK_USER", "question": "Sorry, I encountered an error while analyzing the page. Could you please clarify what you want me to do?"}'


def call_gemini_text(user_message):
    """
    Calls the Gemini API with a text prompt, using the genai.Client structure.
    This is for normal conversation when the browser is not active.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "gemini-1.5-flash" # As requested

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text="You are a helpful assistant named Magic Agent. Respond concisely and friendly. To start a browser session, the user can say 'start browser'."),
            ],
        )

        # Stream the response and join the chunks.
        response_chunks = []
        for chunk in client.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=generate_content_config,
        ):
            response_chunks.append(chunk.text)
            
        return "".join(response_chunks)

    except Exception as e:
        print(f"Error calling Gemini Text API: {e}")
        return "Sorry, I encountered an error. Please try again later."

# --- WhatsApp Communication ---
def send_whatsapp_message(to_number, message):
    """Sends a standard text message via the WhatsApp API."""
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
    if response.status_code == 200:
        print(f"Message sent to {to_number} successfully.")
    else:
        print(f"Failed to send message: {response.status_code} - {response.text}")

def send_whatsapp_image(to_number, image_path, caption=""):
    """
    Sends an image to the user.
    NOTE: The WhatsApp Cloud API requires a public URL for images.
    This function would need to upload the image to a hosting service (like imgur or a cloud bucket)
    to get a public URL first. For this implementation, we will send a text notification
    as a placeholder for the actual image.
    """
    # Placeholder implementation:
    message = caption
    if not caption:
        message = f"Magic Agent performed an action."
    message += f"\n\n(A screenshot was taken to reflect the new state.)"
    send_whatsapp_message(to_number, message)


# --- Webhook Logic ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Handles the webhook verification challenge from Meta.
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        else:
            return Response(status=403)

    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2)) # Log incoming messages for debugging

        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message_info["from"]
            user_message = message_info["text"]["body"]

            session = get_user_session(from_number)

            if not session.get("browsing"):
                # --- NORMAL CHAT MODE ---
                if "start browser" in user_message.lower():
                    send_whatsapp_message(from_number, "Magic Agent is starting the browser...")
                    driver = start_browser(from_number)
                    if driver:
                        time.sleep(2) # Allow browser to initialize
                        screenshot_path = take_screenshot(driver, from_number)
                        send_whatsapp_image(from_number, screenshot_path, caption="Browser is ready. What should I do first?")
                    else:
                        send_whatsapp_message(from_number, "Sorry, I failed to start the browser. Please check the server logs.")
                else:
                    response = call_gemini_text(user_message)
                    send_whatsapp_message(from_number, response)
            else:
                # --- BROWSER CONTROL MODE ---
                driver = session["driver"]
                screenshot_path = take_screenshot(driver, from_number)
                ai_response_text = call_gemini_vision(user_message, screenshot_path)
                
                print(f"AI Command Received: {ai_response_text}")

                try:
                    # The AI's response should be a clean JSON string.
                    # We remove potential markdown formatting like ```json ... ```
                    if ai_response_text.strip().startswith("```json"):
                        ai_response_text = ai_response_text.strip()[7:-4]

                    ai_command = json.loads(ai_response_text)
                    command = ai_command.get("command")

                    action_taken = True
                    action_message = ""

                    if command == "GOTO":
                        url = ai_command.get("url", "")
                        driver.get(url)
                        action_message = f"Magic Agent is navigating to {url}"
                    elif command == "CLICK":
                        x, y = ai_command.get("x"), ai_command.get("y")
                        ActionChains(driver).move_by_offset(x, y).click().perform()
                        ActionChains(driver).move_by_offset(-x, -y).perform() # Reset offset
                        action_message = f"Magic Agent is clicking at coordinates ({x}, {y})."
                    elif command == "TYPE":
                        x, y, text_to_type = ai_command.get("x"), ai_command.get("y"), ai_command.get("text")
                        ActionChains(driver).move_by_offset(x, y).click().perform()
                        ActionChains(driver).move_by_offset(-x, -y).perform() # Reset offset
                        element = driver.switch_to.active_element
                        element.send_keys(text_to_type)
                        action_message = f"Magic Agent is typing: '{text_to_type}'"
                    elif command == "SCROLL":
                        direction = ai_command.get("direction", "DOWN").upper()
                        scroll_key = Keys.PAGE_DOWN if direction == "DOWN" else Keys.PAGE_UP
                        driver.find_element(By.TAG_NAME, 'body').send_keys(scroll_key)
                        action_message = f"Magic Agent is scrolling {direction.lower()}."
                    elif command == "ASK_USER":
                        send_whatsapp_message(from_number, ai_command.get("question"))
                        action_taken = False # No browser action, just asking user
                    elif command == "END_SESSION":
                        reason = ai_command.get("reason", "Task finished.")
                        send_whatsapp_message(from_number, f"Magic Agent is ending the session: {reason}")
                        close_browser(from_number)
                        action_taken = False
                    else:
                        send_whatsapp_message(from_number, "Magic Agent received an unknown command. Please clarify.")
                        action_taken = False

                    # If a browser action was performed, inform the user and send a new screenshot.
                    if action_taken:
                        send_whatsapp_message(from_number, action_message)
                        time.sleep(2) # Wait for page to render after action
                        new_screenshot = take_screenshot(driver, from_number)
                        send_whatsapp_image(from_number, new_screenshot, caption="This is the current view after the action.")

                except (json.JSONDecodeError, KeyError) as e:
                    send_whatsapp_message(from_number, "Magic Agent had a thought, but it wasn't a valid command. Can you please clarify your instruction?")
                    print(f"AI response was not a valid command JSON: {ai_response_text}. Error: {e}")

        except (KeyError, IndexError, TypeError) as e:
            # This catches errors if the incoming webhook data is not in the expected format.
            print(f"Error processing webhook structure: {e}")
            pass

        return Response(status=200)

if __name__ == '__main__':
    # Create necessary directories on startup.
    if not os.path.exists("profiles"):
        os.makedirs("profiles")
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    print("WhatsApp Bot Server started on http://localhost:5000")
    print("Ensure your Cloudflared tunnel is running and pointing to this port.")
    app.run(port=5000, debug=False)
