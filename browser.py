import os
import json
import requests
import base64
import time
from flask import Flask, request, Response
from google import generativeai as genai
from google.generativeai import types
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image
from io import BytesIO

# --- Configuration ---
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Session and Browser Management ---
user_sessions = {}

def get_user_session(phone_number):
    if phone_number not in user_sessions:
        user_sessions[phone_number] = {
            "browsing": False,
            "driver": None,
            "history": []
        }
    return user_sessions[phone_number]

def start_browser(phone_number):
    session = get_user_session(phone_number)
    if session["browsing"]:
        return session["driver"]

    profile_path = os.path.join(os.getcwd(), "profiles", phone_number)
    if not os.path.exists(profile_path):
        os.makedirs(profile_path)

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-data-dir={profile_path}")
    chrome_options.add_argument("--window-size=1280,720")

    driver = webdriver.Chrome(options=chrome_options)
    session["browsing"] = True
    session["driver"] = driver
    return driver

def close_browser(phone_number):
    session = get_user_session(phone_number)
    if session["browsing"] and session["driver"]:
        session["driver"].quit()
        session["browsing"] = False
        session["driver"] = None

def take_screenshot(driver, phone_number):
    screenshot_path = os.path.join(os.getcwd(), "screenshots")
    if not os.path.exists(screenshot_path):
        os.makedirs(screenshot_path)
    
    file_path = os.path.join(screenshot_path, f"{phone_number}.png")
    driver.save_screenshot(file_path)
    return file_path

# --- Gemini AI Interaction ---
def call_gemini_vision(prompt, image_path, phone_number):
    client = genai.Client(api_key=GEMINI_API_KEY)
    model = client.models.get("gemini-1.5-flash") # Using a vision-capable model

    with open(image_path, "rb") as image_file:
        image_data = base64.b64encode(image_file.read()).decode('utf-8')

    system_prompt = """
    You are Magic Agent, an AI assistant with the ability to control a web browser.
    You will be given a prompt from a user and a screenshot of the current browser state.
    Your goal is to respond with a JSON object containing commands to interact with the browser.

    Available commands:
    - {"command": "GOTO", "url": "https://www.google.com"} - Navigates to a URL.
    - {"command": "CLICK", "x": 350, "y": 500} - Clicks on a specific coordinate.
    - {"command": "TYPE", "x": 350, "y": 500, "text": "Hello world"} - Clicks on a coordinate and types text.
    - {"command": "SCROLL", "direction": "DOWN"} - Scrolls the page ('UP' or 'DOWN').
    - {"command": "ASK_USER", "question": "What should I search for?"} - Asks the user for more information.
    - {"command": "END_SESSION", "reason": "I have completed the task."} - Ends the browsing session.

    Analyze the screenshot and the user's prompt to determine the next best action.
    Be precise with your coordinates. The image resolution is 1280x720.
    """

    contents = [
        types.Part.from_text(prompt),
        types.Part.from_data(
            mime_type="image/png",
            data=base64.b64decode(image_data)
        )
    ]
    
    response = model.generate_content(
        contents=contents,
        system_instruction=system_prompt
    )
    return response.text

def call_gemini_text(user_message):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "gemini-1.5-flash"
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text="You are a helpful assistant named Magic Agent. Respond concisely and friendly."),
            ],
        )
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=generate_content_config,
        )
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return "Sorry, I encountered an error. Please try again later."

# --- WhatsApp Communication ---
def send_whatsapp_message(to_number, message):
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
        print(f"Failed to send message: {response.status_code} - {response.text}")

def send_whatsapp_image(to_number, image_path, caption=""):
    # This requires uploading the image first, as WhatsApp API needs a public URL or an ID
    # For simplicity, we'll send the caption and a note that an image was generated.
    # A full implementation would require a service to host the image temporarily.
    send_whatsapp_message(to_number, f"{caption}\n[Image of browser action at {time.ctime()}]")


# --- Webhook Logic ---
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return Response(request.args.get('hub.challenge'), status=200)
        else:
            return Response(status=403)

    if request.method == 'POST':
        body = request.get_json()
        try:
            message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
            from_number = message_info["from"]
            user_message = message_info["text"]["body"]

            session = get_user_session(from_number)

            if not session["browsing"]:
                if "start browser" in user_message.lower():
                    send_whatsapp_message(from_number, "Magic Agent is starting the browser...")
                    driver = start_browser(from_number)
                    time.sleep(2) # Allow browser to initialize
                    screenshot_path = take_screenshot(driver, from_number)
                    send_whatsapp_image(from_number, screenshot_path, "Browser is ready. What should I do first?")
                else:
                    response = call_gemini_text(user_message)
                    send_whatsapp_message(from_number, response)
            else:
                driver = session["driver"]
                screenshot_path = take_screenshot(driver, from_number)
                ai_response_text = call_gemini_vision(user_message, screenshot_path, from_number)
                
                try:
                    ai_command = json.loads(ai_response_text)
                    command = ai_command.get("command")

                    if command == "GOTO":
                        driver.get(ai_command["url"])
                        send_whatsapp_message(from_number, f"Magic Agent is navigating to {ai_command['url']}")
                    elif command == "CLICK":
                        ActionChains(driver).move_by_offset(ai_command["x"], ai_command["y"]).click().perform()
                        send_whatsapp_message(from_number, f"Magic Agent is clicking at ({ai_command['x']}, {ai_command['y']})")
                    elif command == "TYPE":
                        element = driver.switch_to.active_element
                        element.send_keys(ai_command["text"])
                        send_whatsapp_message(from_number, f"Magic Agent is typing: '{ai_command['text']}'")
                    elif command == "SCROLL":
                        if ai_command["direction"] == "DOWN":
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                        else:
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_UP)
                        send_whatsapp_message(from_number, f"Magic Agent is scrolling {ai_command['direction'].lower()}.")
                    elif command == "ASK_USER":
                        send_whatsapp_message(from_number, ai_command["question"])
                        return Response(status=200) # Wait for user's response
                    elif command == "END_SESSION":
                        send_whatsapp_message(from_number, f"Magic Agent is ending the session: {ai_command['reason']}")
                        close_browser(from_number)
                        return Response(status=200)

                    time.sleep(2) # Wait for action to complete
                    new_screenshot = take_screenshot(driver, from_number)
                    send_whatsapp_image(from_number, new_screenshot, "This is the current view.")

                except (json.JSONDecodeError, KeyError) as e:
                    send_whatsapp_message(from_number, "Magic Agent had a thought, but it wasn't a command. Can you clarify?")
                    print(f"AI response was not a valid command: {ai_response_text}")

        except Exception as e:
            print(f"Error processing webhook: {e}")
            pass

        return Response(status=200)

if __name__ == '__main__':
    if not os.path.exists("profiles"):
        os.makedirs("profiles")
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
    print("WhatsApp Bot Server started on http://localhost:5000")
    app.run(port=5000, debug=False)
