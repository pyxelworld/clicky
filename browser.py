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
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import google.generativeai as genai
import pyautogui # For controlling the system cursor and keyboard

# --- CONFIGURATION ---
GEMINI_API_KEYS = [
    # Your API keys
    "AIzaSyCnnkNB4qPXE9bgTwRH_Jj5lxUOq_xivJo", "AIzaSyDuAT3AP1wNd-FNb0QmvwQcSTD2dM3ZStc", "AIzaSyCuKxOa7GoY6id_aG-C3_uhvfJ1iI0SeQ0", "AIzaSyBwASUXeAVJ6xFFZdfjNZO5Hsumr4KAntw", "AIzaSyB4EZanzOFSu589lfBVO3M8dy72fBW2ObY", "AIzaSyASbyRix7Cbae7qCgPQntshA5DVJSVJbo4", "AIzaSyD07UM2S3qdSUyyY0Hp4YtN04J60PcO41w", "AIzaSyA9037TcPXJ2tdSrEe-hzLCn0Xa5zjiUOo",
]
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "645781611962423"
VERIFY_TOKEN = "121222220611"
AI_MODEL_NAME = "gemini-2.5-flash"
ADMIN_NUMBER = "5511990007256" # Administrator number for forwarding

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
SUBSCRIBERS_FILE = BASE_DIR / "subscribers.txt"
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- SUBSCRIBER MANAGEMENT ---
def load_subscribers():
    """Loads subscriber numbers from subscribers.txt into a set."""
    if not SUBSCRIBERS_FILE.exists():
        print(f"'{SUBSCRIBERS_FILE.name}' not found. Please create it with one phone number per line.")
        return set()
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            subscribers = {line.strip() for line in f if line.strip()}
        print(f"Loaded {len(subscribers)} subscribers.")
        return subscribers
    except IOError as e:
        print(f"CRITICAL: Could not read subscribers file: {e}")
        return set()

subscribers = load_subscribers()

# --- CONSTANTS ---
CUSTOM_SEARCH_URL_BASE = "https://www.bing.com"
CUSTOM_SEARCH_URL_TEMPLATE = "https://www.bing.com/search?q=%s"
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are "Magic Agent," a powerful AI that controls a web browser with high precision. You see the screen and choose the best command to achieve your goal.

--- YOUR CORE MECHANISM: DUAL-MODE CURSOR CONTROL ---

You control a large red dot (your virtual cursor). To interact, you MUST first move the cursor to the target, then act. You have two ways to move the cursor. Choose the best one for the job.

1.  **Text Mode (Primary Choice for Text): MOVE_CURSOR_TEXT**
    *   **How it works:** You provide a string of text that you see on the screen. The system uses OCR to find this text and instantly moves the cursor to its center. This is the FASTEST and MOST ACCURATE method for clicking buttons, links, or anything with a clear text label.
    *   **Usage:** `{"command": "MOVE_CURSOR_TEXT", "params": {"text": "Login"}}`
2.  **Coordinate Mode (For Visual Elements): MOVE_CURSOR_COORDS**
    *   **How it works:** The screen has a subtle gray grid with numbered axes. Use this grid to estimate the (x, y) coordinates of your target. This is best for clicking on icons, images, or areas without any text.
    *   **Usage:** `{"command": "MOVE_CURSOR_COORDS", "params": {"x": 120, "y": 455}}`

--- THE MANDATORY WORKFLOW: MOVE -> VERIFY -> ACT ---

This 3-step process is ESSENTIAL.

1.  **MOVE:** Issue either a `MOVE_CURSOR_TEXT` or `MOVE_CURSOR_COORDS` command.
2.  **VERIFY:** You will receive a new screenshot. CRITICALLY, EXAMINE IT. Is the red dot EXACTLY on your target?
3.  **ACT:**
    *   If the dot is correct, issue your action command (`CLICK`, `CLEAR`, etc.).
    *   If the dot is slightly off, DO NOT CLICK. Issue another `MOVE_CURSOR` command to correct its position. For text, maybe try a shorter or different part of the text. For coordinates, adjust the numbers.

--- YOUR RESPONSE FORMAT ---
Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

== CURSOR MOVEMENT & ACTION COMMANDS ==
1.  **MOVE_CURSOR_TEXT**: Moves the cursor to the center of the specified text found by OCR.
    - Params: `{"text": "<text_on_screen>"}`
2.  **MOVE_CURSOR_COORDS**: Moves the cursor to a specific (x, y) coordinate. Use the visual grid for reference.
    - Params: `{"x": <int>, "y": <int>}`
3.  **CLICK**: Performs a REAL system-level mouse click at the cursor's current location. Must be used after moving the cursor.
    - Params: `{}`
4.  **TYPE**: Types text using the system keyboard. You MUST CLICK an input field first.
    - Params: `{"text": "<text_to_type>", "enter": <true/false>}`
5.  **CLEAR**: Clears the input field under the cursor by selecting all and deleting.
    - Params: `{}`
6.  **SCROLL**: Scrolls the page using the system scroll wheel.
    - Params: `{"direction": "<up|down>"}`

== BROWSER & NAVIGATION COMMANDS ==
7.  **END_BROWSER**: Closes the browser when the task is fully complete.
    - Params: `{"reason": "<summary>"}`
8.  **NAVIGATE**: Goes directly to a URL. IF YOU KNOW THE URL, GO DIRECTLY.
    - Params: `{"url": "<full_url>"}`
9.  **CUSTOM_SEARCH**: Performs a search using "Bing".
    - Params: `{"query": "<search_term>"}`
10. **GO_BACK**: Navigates to the previous page in history.
    - Params: `{}`
11. **GET_CURRENT_URL**: Gets the URL of the current page. The URL will be shown to you in the next step to confirm your location.
    - Params: `{}`

== TAB MANAGEMENT COMMANDS ==
12. **NEW_TAB**: Opens a new browser tab.
13. **SWITCH_TO_TAB**: Switches to an existing tab by its ID number.
14. **CLOSE_TAB**: Closes the current tab.

== USER INTERACTION COMMANDS ==
15. **PAUSE_AND_ASK**: Pauses to ask the user a question.
    - Params: `{"question": "<your_question>"}`
16. **SPEAK**: For simple conversation when no browser action is needed.
    - Params: `{"text": "<your_response>"}`

-- ERROR RECOVERY ---
If a command fails, the page may have changed. Analyze the new screenshot and the error message. Do not repeat the failed command. Issue a new command to recover.

--- GUIDING PRINCIPLES ---
*   **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down on a page after it loads or after an action to understand the full context.
*   **SEARCH STRATEGY:** Use `CUSTOM_SEARCH` with "Bing". Do NOT use `NAVIGATE` to go to other search engines.
*   **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt it. Stop and ask the user for permission using `PAUSE_AND_ASK`.
*   **SHOPPING STRATEGY:** Use `PAUSE_AND_ASK` to clarify product and price. Use sorting/filtering features on sites.
*   **POPUPS AND COOKIES:** IGNORE THEM. Do NOT click accept or reject. Just continue with your task.
*   IF YOU KNOW A WEBSITE'S URL, USE IT TO DIRECTLY GO TO IT WITHOUT USING SEARCH ENGINES (`NAVIGATE` TOOL).
*   ALWAYS TRY TO USE SEARCH BARS AS LITTLE AS POSSIBLE. IF YOU CAN USE THE NAVIGATE TOOL TO ALREADY GO TO A WEBSITE AND SEARCH ON IT WITH THE QUERY ON THE LINK (example https://lista.mercadolivre.com.br/QUERY) DO IT.

--- LANGUAGE ---
Always speak the same language the user used.

--- MAGIC AND YOU ---
You are built by Pyxel (pyxelworld.com). Another AI, Magic, can handle tasks you can't (like non-browser tasks or handling files).
If you cannot do something, direct the user to Magic at https://wa.me/551127375623 or https://askmagic.com.br.
You can create direct links for the user, for example: https://wa.me/551127375623?text=gere+uma+imagem+de+um+gato.

REMEMBER THAT ONLY WHAT YOU "SPEAK" IS SENT TO THE USER!

--- FOLLOW 100% OF THE TIME ---
NEVER ACCEPT/INTERACT WITH COOKIE OR COOKIE BANNERS/POPUPS
IF YOU SEE A POPUP ASKING YOU SOMETHING, IGNORE IT. IF ITS TO ADD LOCATION, CEP, ANYTHING, DO NOT INTERACT WITH IT. FOCUS ON YOUR GOAL. AND YOUR GOAL IS NOT ADDING AN ADDRRESS OR ACCEPTING COOKIES.
NEVER USE SEARCH BOXES. ALREADY INPUT THE SEARCH YOU WANT IN THE URL TO SPEED UP THE PROCESS.
"""

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "text": {"body": text}};
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Sent text message to {to}: {text[:80]}...")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp text message: {e} - {response.text}")

def send_whatsapp_image(to, image_path, caption=""):
    upload_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/media"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}; files = {'file': (image_path.name, open(image_path, 'rb'), 'image/png'), 'messaging_product': (None, 'whatsapp'), 'type': (None, 'image/png')}; media_id = None
    try: response = requests.post(upload_url, headers=headers, files=files); response.raise_for_status(); media_id = response.json().get('id')
    except requests.exceptions.RequestException as e: print(f"Error uploading WhatsApp media: {e} - {response.text}"); return
    if not media_id: print("Failed to get media ID."); return
    send_url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}; data = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"id": media_id, "caption": caption}}
    try: requests.post(send_url, headers=headers, json=data).raise_for_status(); print(f"Sent image message to {to} with caption: {caption}")
    except requests.exceptions.RequestException as e: print(f"Error sending WhatsApp image message: {e} - {response.text}")

def send_whatsapp_document_by_id(to, media_id, caption="", filename="document.pdf"):
    """Sends a document using an existing media ID."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"; headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": {"id": media_id, "filename": filename, "caption": caption}}
    try: response = requests.post(url, headers=headers, json=data); response.raise_for_status(); print(f"Forwarded document {media_id} to {to}")
    except requests.exceptions.RequestException as e: print(f"Error forwarding WhatsApp document: {e} - {response.text}")

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        print(f"Creating new session for {phone_number}")
        user_dir = USER_DATA_DIR / phone_number
        session = {
            "mode": "CHAT", "driver": None, "chat_history": [], "original_prompt": "",
            "user_dir": user_dir, "tab_handles": {}, "is_processing": False,
            "stop_requested": False, "interrupt_requested": False,
            "cursor_pos": (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2),
            "ocr_results": []
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance..."); options = Options(); options.add_argument("--no-sandbox"); options.add_argument("--disable-dev-shm-usage"); options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}"); options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        # Give the window focus for pyautogui
        time.sleep(1) # Wait for window to appear
        driver.switch_to.window(driver.current_window_handle)
        pyautogui.click(pyautogui.locateCenterOnScreen(driver.get_screenshot_as_png())) # A trick to focus the window
        time.sleep(0.5)
        session["driver"] = driver; session["mode"] = "BROWSER"; return driver
    except Exception as e: print(f"CRITICAL: Error starting Selenium browser: {e}"); traceback.print_exc(); return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try:
            session["driver"].quit()
        except Exception as e:
            print(f"Error during browser quit: {e}")
        finally:
            session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["tab_handles"] = {}; session["cursor_pos"] = (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2); session["ocr_results"] = []

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    tab_info_text = "Could not get tab info."
    try:
        window_handles = driver.window_handles; current_handle = driver.current_window_handle; tabs = []; session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1; session["tab_handles"][tab_id] = handle;
            driver.switch_to.window(handle);
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e: print(f"Could not get tab info: {e}")

    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        
        try:
            ocr_data = pytesseract.image_to_data(image, lang='por+eng', output_type=pytesseract.Output.DICT)
            session['ocr_results'] = ocr_data
            print(f"OCR executed. Found {len(ocr_data.get('text', []))} words.")
        except Exception as e:
            print(f"Tesseract/OCR error: {e}. Is tesseract-ocr installed and in your PATH?")
            session['ocr_results'] = {}

        draw = ImageDraw.Draw(image, 'RGBA')
        try: font = ImageFont.truetype("DejaVuSans.ttf", size=10)
        except IOError: font = ImageFont.load_default()

        grid_color = (0, 0, 0, 100)
        for i in range(100, VIEWPORT_WIDTH, 100):
            draw.line([(i, 0), (i, VIEWPORT_HEIGHT)], fill=grid_color, width=1)
            draw.text((i + 2, 2), str(i), fill='red', font=font)
        for i in range(100, VIEWPORT_HEIGHT, 100):
            draw.line([(0, i), (VIEWPORT_WIDTH, i)], fill=grid_color, width=1)
            draw.text((2, i + 2), str(i), fill='red', font=font)

        cursor_x, cursor_y = session['cursor_pos']; radius = 16; outline_width = 4
        draw.ellipse([(cursor_x - radius, cursor_y - radius), (cursor_x + radius, cursor_y + radius)], fill='white')
        draw.ellipse([(cursor_x - (radius-outline_width), cursor_y-(radius-outline_width)), (cursor_x+(radius-outline_width), cursor_y+(radius-outline_width))], fill='red')
        
        image.save(screenshot_path)
        print(f"State captured with grid and cursor at {session['cursor_pos']}.")
        return screenshot_path, tab_info_text
    except Exception as e:
        print(f"Error getting page state: {e}"); traceback.print_exc()
        return None, tab_info_text

def find_text_in_ocr(ocr_results, target_text):
    n_boxes = len(ocr_results.get('text', [])); target_words = target_text.lower().split();
    if not target_words: return None
    for i in range(n_boxes):
        match_words = []; temp_left, temp_top, temp_right, temp_bottom = float('inf'), float('inf'), 0, 0
        if target_words[0] in ocr_results['text'][i].lower():
            k = 0
            for j in range(i, n_boxes):
                if k < len(target_words) and ocr_results['conf'][j] > 40:
                    word_lower = ocr_results['text'][j].lower()
                    if target_words[k] in word_lower:
                        match_words.append(ocr_results['text'][j]);(x, y, w, h) = (ocr_results['left'][j], ocr_results['top'][j], ocr_results['width'][j], ocr_results['height'][j]);temp_left = min(temp_left, x); temp_top = min(temp_top, y); temp_right = max(temp_right, x + w); temp_bottom = max(temp_bottom, y + h);k += 1
                    # Allow skipping over irrelevant words in between
                elif ocr_results['text'][j].strip() == "":
                    continue
                else:
                    break # Break if the sequence is broken
            if k == len(target_words):
                print(f"OCR Match found for '{target_text}': '{' '.join(match_words)}'")
                return {"left": temp_left, "top": temp_top, "width": temp_right - temp_left, "height": temp_bottom - temp_top, "text": ' '.join(match_words)}
    return None

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try: prompt_parts.append(Image.open(image_path))
        except Exception as e: return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: {e}"}, "thought": "Image read failed.", "speak": "Erro com a visualização da tela."})
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}..."); genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
            chat = model.start_chat(history=chat_history); response = chat.send_message(prompt_parts); print("AI call successful.")
            return response.text
        except Exception as e: print(f"API key #{i+1} failed. Error: {e}"); last_error = e; continue
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Erro ao conectar com meu cérebro."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\nCurrent Screen State:\n{tab_info_text}\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "[Sistema] Não foi possível ver o navegador, fechando..."); close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    if session.get("stop_requested"): print("Stop was requested."); session.clear(); return {}
    if session.get("interrupt_requested"): print("Interrupt was requested."); session["interrupt_requested"] = False; return {}
    
    try: command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, f"[Sistema] IA respondeu formato inválido: {ai_response_text}");
        if session["mode"] == "BROWSER": session["is_processing"] = False; send_whatsapp_message(from_number, "[Sistema] IA confusa. Diga o que fazer.")
        return {}

    command, params, thought, speak = command_data.get("command"), command_data.get("params", {}), command_data.get("thought", ""), command_data.get("speak", "")
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak: send_whatsapp_message(from_number, speak)

    driver = session.get("driver")
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER", "PAUSE_AND_ASK"]:
        send_whatsapp_message(from_number, "[Sistema] Navegador não aberto. Abrindo e tentando de novo..."); driver = start_browser(session);
        if not driver: send_whatsapp_message(from_number, "[Sistema] Falha crítica ao iniciar navegador."); close_browser(session); return {}
        time.sleep(1); return process_ai_command(from_number, ai_response_text)

    try:
        action_in_browser = True; next_step_caption = f"[Sistema] O Agent executou: {command}"
        
        # --- COORDINATE TRANSLATION LOGIC ---
        # This is the fix for pyautogui's screen-relative coordinates.
        try:
            # Get the browser window's top-left corner on the screen.
            browser_pos = driver.get_window_position()
            browser_x, browser_y = browser_pos['x'], browser_pos['y']
            
            # Get the size of the browser's "chrome" (title bar, address bar, etc.)
            chrome_size_js = "return [window.outerWidth - window.innerWidth, window.outerHeight - window.innerHeight];"
            chrome_width, chrome_height = driver.execute_script(chrome_size_js)

            # The content area's top-left corner on the screen
            # This is our offset for all pyautogui actions.
            content_area_x = browser_x + (chrome_width / 2) # Assume border is symmetrical
            content_area_y = browser_y + chrome_height
        except Exception as e:
            print(f"Warning: Could not get precise window offsets: {e}. Falling back to 0,0.")
            content_area_x, content_area_y = 0, 0
        # --- END OF COORDINATE TRANSLATION LOGIC ---

        if command == "MOVE_CURSOR_COORDS":
            session['cursor_pos'] = (params.get("x", 0), params.get("y", 0))
            action_in_browser = False
        elif command == "MOVE_CURSOR_TEXT":
            target_text = params.get("text")
            if not target_text: next_step_caption = "[Sistema] Erro: Tentou usar MOVE_CURSOR_TEXT sem texto."
            else:
                found_box = find_text_in_ocr(session.get('ocr_results', {}), target_text)
                if found_box:
                    session['cursor_pos'] = (found_box['left'] + found_box['width'] // 2, found_box['top'] + found_box['height'] // 2)
                    next_step_caption = f"[Sistema] Cursor movido para o texto '{found_box['text']}'."
                else:
                    next_step_caption = f"[Sistema] ERRO: O texto '{target_text}' não foi encontrado na tela. Tente um texto diferente ou use coordenadas."
            action_in_browser = False
        
        elif command == "CLICK":
            cursor_x, cursor_y = session['cursor_pos']
            # Translate window-relative coords to ACCURATE screen-relative coords
            screen_x = content_area_x + cursor_x
            screen_y = content_area_y + cursor_y
            pyautogui.moveTo(screen_x, screen_y, duration=0.25)
            pyautogui.click()
            next_step_caption = f"[Sistema] Clicou nas coordenadas ({cursor_x}, {cursor_y})."
        elif command == "TYPE":
            pyautogui.write(params.get("text", ""), interval=0.05)
            if params.get("enter", False):
                pyautogui.press('enter')
        elif command == "CLEAR":
            cursor_x, cursor_y = session['cursor_pos']
            # Translate coords for the click to focus the field
            screen_x = content_area_x + cursor_x
            screen_y = content_area_y + cursor_y
            pyautogui.moveTo(screen_x, screen_y, duration=0.25)
            pyautogui.click()
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.press('delete')
        elif command == "SCROLL":
            scroll_amount = 500 if params.get('direction', 'down') == 'down' else -500
            pyautogui.scroll(scroll_amount)
            
        elif command == "START_BROWSER":
            driver = start_browser(session); time.sleep(1); driver.get(CUSTOM_SEARCH_URL_BASE)
        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "GET_CURRENT_URL":
            try: current_url = driver.current_url; next_step_caption = f"[Sistema] URL atual: {current_url}"
            except Exception as e: next_step_caption = f"[Sistema] Erro ao obter URL: {e}"
            action_in_browser = False
        elif command == "END_BROWSER":
            send_whatsapp_message(from_number, f"*Tarefa Concluída.*\n*Sumário:* {params.get('reason', 'N/A')}"); close_browser(session); return command_data
        elif command == "PAUSE_AND_ASK" or command == "SPEAK":
            session["is_processing"] = False; return command_data
        else:
            send_whatsapp_message(from_number, f"[Sistema] Comando desconhecido: {command}"); action_in_browser = False
        
        if action_in_browser: time.sleep(2)
        process_next_browser_step(from_number, session, next_step_caption)
    except Exception as e:
        error_summary = f"Erro no comando '{command}': {e}"; print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        time.sleep(1); process_next_browser_step(from_number, session, caption=f"Ocorreu um erro: {error_summary}. O que devo fazer agora?")
    return command_data

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
            message_id = message_info.get("id")
            if message_id in processed_message_ids:
                print(f"Duplicate message ID {message_id} ignored.")
                return Response(status=200)
            processed_message_ids.add(message_id)

            from_number = message_info["from"]
            message_type = message_info.get("type")

            if from_number not in subscribers:
                print(f"Received message from non-subscriber: {from_number}")
                if message_type == "document":
                    doc_info = message_info.get("document", {})
                    media_id = doc_info.get("id")
                    filename = doc_info.get("filename", "comprovante.pdf")
                    if media_id:
                        send_whatsapp_document_by_id(ADMIN_NUMBER, media_id, filename=filename, caption=f"Comprovante de: {from_number}")
                        send_whatsapp_message(ADMIN_NUMBER, f"Novo comprovante recebido de: {from_number}")
                    reply_text = "Obrigado por assinar!\nNossos administradores irão verificar o documento e te dar acesso em breve.\n\nPara receber atualizações sobre seu acesso, não esqueça de ter uma conta Magic. É só falar com ele em https://wa.me/551127275623"
                    send_whatsapp_message(from_number, reply_text)
                else: 
                    reply_text = "O Magic Agent é uma IA dos mesmos criadores do Magic que tem acesso a um navegador completo (como o que você usa todos os dias), possibilitando ele de fazer ações na internet por você.\n\nVocê pode acessar o Magic Agent fazendo um Pix Recorrente de 10 Reais todo mês para a chave Pix *magicagent@askmagic.com.br*.\nEnvie o comprovante em PDF aqui para receber acesso.\n\nOu use o Magic sem acesso ao navegador em https://askmagic.com.br"
                    send_whatsapp_message(from_number, reply_text)
                return Response(status=200)
            
            if message_type != "text":
                send_whatsapp_message(from_number, "[Sistema] Suporto apenas mensagens de texto.")
                return Response(status=200)
            
            user_message_text = message_info["text"]["body"]
            print(f"Received from subscriber {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            command_text = user_message_text.strip().lower()

            if command_text == "/stop":
                print(f"User {from_number} issued /stop command."); session["stop_requested"] = True; close_browser(session); session["is_processing"] = False
                send_whatsapp_message(from_number, "[Sistema] Ação cancelada e sessão encerrada."); return Response(status=200)

            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                if session["mode"] != "BROWSER": send_whatsapp_message(from_number, "[Sistema] Nenhuma ação em andamento para interromper.")
                else: session["interrupt_requested"] = True; session["is_processing"] = False; send_whatsapp_message(from_number, "[Sistema] Ação interrompida. Me diga como continuar.")
                return Response(status=200)

            if command_text == "/clear":
                print(f"User {from_number} issued /clear command."); close_browser(session)
                if from_number in user_sessions: del user_sessions[from_number]
                send_whatsapp_message(from_number, "[Sistema] Memória e navegador limpos."); print(f"Session for {from_number} cleared.")
                return Response(status=200)

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "[Sistema] Trabalhando... Use /interrupt ou /stop."); return Response(status=200)
            
            command_data = {}
            try:
                session["is_processing"] = True; session["chat_history"].append({"role": "user", "parts": [user_message_text]})
                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=f"New task: {user_message_text}")
                    command_data = process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    process_next_browser_step(from_number, session, f"[User Guidance]: {user_message_text}")
            finally:
                if not session.get("interrupt_requested") and command_data.get("command") not in ["PAUSE_AND_ASK", "SPEAK"]:
                    session["is_processing"] = False
        except (KeyError, IndexError, TypeError):
            pass
        except Exception as e:
            print(f"Error processing webhook: {e}"); traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server (System Cursor v1.2 - Accurate) ---")
    app.run(host='0.0.0.0', port=5000, debug=False)
