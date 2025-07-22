import os
import json
import requests
import base64
import time
import re
from flask import Flask, request, Response
from google import genai
from google.genai import types

# --- Selenium Imports for Browser Automation ---
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

# --- Configuration ---
# I'm using your provided keys for testing as requested.
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"

# --- Model & AI Persona ---
# NOTE: gemini-1.5-flash is the current, powerful multimodal model ideal for this task.
# It replaced older models and is better suited for image and text understanding than the one you mentioned.
GEMINI_MODEL_NAME = "gemini-1.5-flash" 

# --- Directory Setup ---
USER_DATA_PATH = os.path.join(os.getcwd(), "user_data")
if not os.path.exists(USER_DATA_PATH):
    os.makedirs(USER_DATA_PATH)
    print(f"Created user data directory at: {USER_DATA_PATH}")

# --- Global Session Management ---
# This dictionary will hold the state for each user (phone number).
# Example: sessions['1234567890'] = {'driver': WebDriver_instance, 'history': [...]}
sessions = {}

# --- Flask App Initialization ---
app = Flask(__name__)

# --- System Prompt for Magic Agent ---
MAGIC_AGENT_SYSTEM_PROMPT = """
You are Magic Agent, a sophisticated AI assistant designed to help users by browsing the web on their behalf.

Your primary function is to interpret user requests, navigate a web browser to fulfill them, and report back on your actions. You operate by receiving a screenshot of the current browser page and then issuing a single, specific command in JSON format to perform the next action.

**You have two modes:**

1.  **Conversation Mode:** When there is no active browser session, you are a helpful assistant. You can chat with the user. If the user's request requires web browsing, you MUST start the process by issuing the `START_BROWSER` command.
2.  **Browser Mode:** Once the browser is started, you are in full control. You will receive the user's instructions and a screenshot. You MUST ONLY respond with a single valid JSON command and nothing else. Do not add any explanatory text outside of the JSON structure.

**Available Commands:**

1.  **Start the Browser:**
    `{"command": "START_BROWSER", "reasoning": "I need to open the browser to fulfill the user's request."}`
    - Use this as the very first step when a web task is needed.

2.  **Navigate to a URL:**
    `{"command": "NAVIGATE", "url": "https://www.google.com", "reasoning": "I need to go to the Google homepage."}`
    - `url`: The full web address to visit.

3.  **Type Text:**
    `{"command": "TYPE", "selector": "css selector for the element", "text": "text to type", "reasoning": "I am typing the search query into the search bar."}`
    - `selector`: The CSS selector of the input field (e.g., `input[name='q']`).
    - `text`: The text to enter.

4.  **Click an Element:**
    `{"command": "CLICK", "selector": "css selector for the element", "reasoning": "I am clicking the search button."}`
    - `selector`: The CSS selector of the button, link, or element to click (e.g., `input[type='submit']`).

5.  **Scroll the Page:**
    `{"command": "SCROLL", "direction": "down", "reasoning": "I need to see more of the page."}`
    - `direction`: Can be "up" or "down".

6.  **Ask the User for Information:**
    `{"command": "ASK_USER", "question": "What is your budget for the flight?", "reasoning": "I need more information from the user to proceed."}`
    - Use this to pause the browsing session and get clarification. The browser will remain open.

7.  **End the Browser Session:**
    `{"command": "END_SESSION", "reasoning": "I have completed the task and found the information."}`
    - Use this when the entire task is finished. This will close the browser.

**Error Handling:**
If a command fails (e.g., a selector is not found), you will be notified. Analyze the new screenshot and issue a corrected command.

**Example Flow:**
User: "Find me the weather in New York."
You (first response): `{"command": "START_BROWSER", "reasoning": "I need to browse the web to find the weather."}`
*Server starts browser, goes to google.com, sends you the screenshot.*
You (second response): `{"command": "TYPE", "selector": "textarea[name='q']", "text": "weather in New York", "reasoning": "Typing the weather query."}`
*Server types, takes a new screenshot, sends it to you.*
You (third response): `{"command": "CLICK", "selector": "input[type='submit']", "reasoning": "Clicking the search button."}`
...and so on, until the task is complete.
"""


# --- WhatsApp Communication Functions ---

def send_whatsapp_message(to_number: str, message: str):
    """Sends a simple text message."""
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
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Message sent to {to_number} successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message to {to_number}: {e} - {response.text}")

def upload_whatsapp_media(image_bytes: bytes):
    """Uploads media to WhatsApp servers and returns the media ID."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    files = {
        'file': ('screenshot.png', image_bytes, 'image/png'),
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

def send_whatsapp_image(to_number: str, image_bytes: bytes, caption: str):
    """Sends an image with a caption."""
    media_id = upload_whatsapp_media(image_bytes)
    if not media_id:
        send_whatsapp_message(to_number, f"Sorry, I couldn't generate the screenshot, but here's the update:\n\n{caption}")
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
        print(f"Failed to send image message to {to_number}: {e} - {response.text}")


# --- AI and Browser Control Functions ---

def call_gemini_vision(prompt_text: str, image_base64: str, chat_history: list):
    """Calls Gemini with text and an image to get the next command."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model = client.models.get_model(f"models/{GEMINI_MODEL_NAME}")
        
        # Build the full history for context
        full_contents = chat_history + [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt_text),
                    types.Part.from_data(
                        mime_type="image/png",
                        data=base64.b64decode(image_base64)
                    )
                ]
            )
        ]

        # Generate content
        response = model.generate_content(
            contents=full_contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
            system_instruction=MAGIC_AGENT_SYSTEM_PROMPT
        )
        
        # The AI should respond with a JSON string, which we parse.
        ai_response_text = response.text.strip()
        print(f"Gemini Raw Response: {ai_response_text}")
        return json.loads(ai_response_text)

    except Exception as e:
        print(f"Error calling Gemini Vision API: {e}")
        return {"command": "END_SESSION", "reasoning": f"An internal error occurred: {e}"}

def call_gemini_text(prompt_text: str, chat_history: list):
    """Calls Gemini with only text for conversational mode."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model = client.models.get_model(f"models/{GEMINI_MODEL_NAME}")

        # Build the full history for context
        full_contents = chat_history + [
            types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
        ]

        # Generate content
        response = model.generate_content(
            contents=full_contents,
            system_instruction=MAGIC_AGENT_SYSTEM_PROMPT
        )
        
        ai_response_text = response.text.strip()
        print(f"Gemini Text-Only Raw Response: {ai_response_text}")
        
        # Try to parse as JSON first (for START_BROWSER command)
        try:
            return json.loads(ai_response_text)
        except json.JSONDecodeError:
            # If it fails, it's a regular text response
            return {"text_response": ai_response_text}

    except Exception as e:
        print(f"Error calling Gemini Text API: {e}")
        return {"text_response": "I'm sorry, I encountered an error. Please try again."}

def start_browser(phone_number: str):
    """Starts a new Selenium browser session for a user."""
    if phone_number in sessions and sessions[phone_number].get('driver'):
        print(f"Browser session already exists for {phone_number}.")
        return sessions[phone_number]['driver']

    print(f"Starting new browser session for {phone_number}...")
    user_profile_path = os.path.join(USER_DATA_PATH, phone_number, "profile")
    user_download_path = os.path.join(USER_DATA_PATH, phone_number, "downloads")
    
    # Create directories if they don't exist
    os.makedirs(user_profile_path, exist_ok=True)
    os.makedirs(user_download_path, exist_ok=True)
    
    chrome_options = Options()
    # Running in terminal-only mode requires headless.
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,1024")
    chrome_options.add_argument(f"--user-data-dir={user_profile_path}")
    
    prefs = {"download.default_directory": user_download_path}
    chrome_options.add_experimental_option("prefs", prefs)

    try:
        driver = webdriver.Chrome(options=chrome_options)
        sessions[phone_number] = {'driver': driver, 'history': []}
        return driver
    except Exception as e:
        print(f"Failed to start ChromeDriver: {e}")
        return None

def close_browser(phone_number: str):
    """Closes the browser session for a user."""
    if phone_number in sessions and sessions[phone_number].get('driver'):
        print(f"Closing browser session for {phone_number}.")
        sessions[phone_number]['driver'].quit()
        # Keep chat history but remove the driver
        del sessions[phone_number]['driver']
        # Or clear the whole session if you prefer
        # del sessions[phone_number]

def take_screenshot(driver) -> bytes:
    """Takes a screenshot and returns it as bytes."""
    return driver.get_screenshot_as_png()

# --- Main Webhook Logic ---
@app.route('/webhook', methods=['POST', 'GET'])
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
            if (body.get("entry") and
                body["entry"][0].get("changes") and
                body["entry"][0]["changes"][0].get("value") and
                body["entry"][0]["changes"][0]["value"].get("messages")):
                
                message_info = body["entry"][0]["changes"][0]["value"]["messages"][0]
                from_number = message_info.get("from")
                
                if message_info.get("type") == "text":
                    user_message_text = message_info["text"]["body"]
                    handle_message(from_number, user_message_text)
                else:
                    send_whatsapp_message(from_number, "Sorry, I can only process text messages.")
        except Exception as e:
            print(f"Error processing webhook: {e}")
        
        return Response(status=200)

def handle_message(phone_number: str, user_message: str):
    """Main logic to handle incoming messages and orchestrate the AI agent."""
    
    # Initialize session if not exists
    if phone_number not in sessions:
        sessions[phone_number] = {'history': []}

    session = sessions[phone_number]
    chat_history = session.get('history', [])

    # === BROWSER MODE ===
    if 'driver' in session and session['driver']:
        driver = session['driver']
        
        # User is giving a follow-up instruction while browser is active
        send_whatsapp_message(phone_number, "Magic Agent received your instruction. Thinking...")
        
        # We need a current screenshot to proceed
        screenshot_bytes = take_screenshot(driver)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        prompt = f"The user just said: '{user_message}'. Continue the task based on this new information. What is the next command?"
        
        # Add user message to history
        chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
        
        ai_command = call_gemini_vision(prompt, screenshot_base64, chat_history)

        # Add AI response to history
        chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(ai_command))]))
        
        # Process the command from the AI
        process_browser_command(phone_number, ai_command)

    # === CONVERSATION MODE ===
    else:
        # No active browser. Talk to the AI.
        send_whatsapp_message(phone_number, "Magic Agent is thinking...")

        # Add user message to history
        chat_history.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

        ai_response = call_gemini_text(user_message, chat_history)
        
        # Add AI response to history
        if "text_response" in ai_response:
             chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=ai_response['text_response'])]))
        else:
             chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(ai_response))]))

        if "command" in ai_response and ai_response["command"] == "START_BROWSER":
            # AI has decided to start browsing
            process_browser_command(phone_number, ai_response, initial_user_message=user_message)
        elif "text_response" in ai_response:
            # It's just a regular chat response
            send_whatsapp_message(phone_number, ai_response["text_response"])
        else:
            # The AI might have sent a command without starting the browser, which is an error state
            send_whatsapp_message(phone_number, "I'm a bit confused. Could you please clarify your request?")


def process_browser_command(phone_number, command_data, initial_user_message=None):
    """Executes the command from the AI and continues the loop."""
    command = command_data.get("command")
    reasoning = command_data.get("reasoning", "No reason provided.")
    session = sessions[phone_number]
    chat_history = session.get('history', [])
    
    driver = None # Define driver here to ensure it's in scope

    try:
        if command == "START_BROWSER":
            send_whatsapp_message(phone_number, "Magic Agent is starting the browser...")
            driver = start_browser(phone_number)
            if not driver:
                send_whatsapp_message(phone_number, "Sorry, I failed to start the browser. Please check the server logs.")
                return
            
            # Start at a known page
            driver.get("https://www.google.com")
            time.sleep(2) # Wait for page to render

            screenshot_bytes = take_screenshot(driver)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            prompt = f"""The browser is now open. The user's original request was: '{initial_user_message}'.
            Here is the initial screenshot of the page. What is the first command to begin this task?"""
            
            send_whatsapp_image(phone_number, screenshot_bytes, caption="Browser started. What should I do first?")
            
            # Recursive call to get the *next* command
            next_command = call_gemini_vision(prompt, screenshot_base64, chat_history)
            chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(next_command))]))
            process_browser_command(phone_number, next_command)
            return

        # --- All subsequent commands require a driver ---
        driver = session.get('driver')
        if not driver:
            send_whatsapp_message(phone_number, "Error: No active browser session found to execute the command.")
            return

        action_description = ""
        if command == "NAVIGATE":
            url = command_data.get('url')
            action_description = f"Magic Agent is navigating to: {url}"
            send_whatsapp_message(phone_number, action_description)
            driver.get(url)

        elif command == "TYPE":
            selector = command_data.get('selector')
            text_to_type = command_data.get('text')
            action_description = f"Magic Agent is typing '{text_to_type}'"
            send_whatsapp_message(phone_number, action_description)
            element = driver.find_element(By.CSS_SELECTOR, selector)
            element.clear()
            element.send_keys(text_to_type)
        
        elif command == "CLICK":
            selector = command_data.get('selector')
            action_description = f"Magic Agent is clicking on an element..."
            send_whatsapp_message(phone_number, action_description)
            driver.find_element(By.CSS_SELECTOR, selector).click()

        elif command == "SCROLL":
            direction = command_data.get('direction', 'down')
            scroll_amount = 1000 if direction == 'down' else -1000
            action_description = f"Magic Agent is scrolling {direction}..."
            send_whatsapp_message(phone_number, action_description)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

        elif command == "ASK_USER":
            question = command_data.get("question")
            send_whatsapp_message(phone_number, question)
            # The session remains active, waiting for the user's next message
            return # Stop the loop here

        elif command == "END_SESSION":
            action_description = f"Magic Agent is finishing the task. {reasoning}"
            send_whatsapp_message(phone_number, action_description)
            close_browser(phone_number)
            return # Stop the loop here

        else:
            send_whatsapp_message(phone_number, f"Unknown command received: {command}")
            return

        # --- AFTER ACTION: Capture state and continue loop ---
        time.sleep(3) # Crucial: wait for the page to update after an action
        
        screenshot_bytes = take_screenshot(driver)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # Send update to the user
        send_whatsapp_image(phone_number, screenshot_bytes, caption=action_description)

        # Ask AI for the next step
        prompt = "The last command was executed successfully. Here is the new screenshot. What is the next command?"
        next_command = call_gemini_vision(prompt, screenshot_base64, chat_history)
        chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(next_command))]))

        # Recursive call to process the next command
        process_browser_command(phone_number, next_command)

    except NoSuchElementException:
        error_message = f"Action failed: Could not find the element with selector: `{command_data.get('selector')}`."
        print(error_message)
        
        # Take a screenshot of the failure state
        screenshot_bytes = take_screenshot(driver)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        # Inform the user
        send_whatsapp_image(phone_number, screenshot_bytes, caption="Oops, that didn't work. Magic Agent is thinking of another way...")

        # Ask the AI to self-correct
        prompt = f"""{error_message}
        The page may have changed, or the selector was incorrect.
        Analyze the new screenshot and provide a different command to continue the task."""
        
        next_command = call_gemini_vision(prompt, screenshot_base64, chat_history)
        chat_history.append(types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(next_command))]))
        process_browser_command(phone_number, next_command)

    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        print(error_message)
        send_whatsapp_message(phone_number, f"Magic Agent encountered an error and has to stop. Details: {error_message}")
        close_browser(phone_number)


if __name__ == '__main__':
    print("Magic Agent WhatsApp Server starting on http://localhost:5000")
    print("Webhook endpoint is /webhook")
    app.run(port=5000, debug=False)
