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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# --- CONFIGURATION ---
# Rotating API keys!
GEMINI_API_KEYS = [
    # Suas chaves de API vão aqui. Mantive as do seu código original.
    "AIzaSyCnnkNB4qPXE9bgTwRH_Jj5lxUOq_xivJo",
    "AIzaSyDuAT3AP1wNd-FNb0QmvwQcSTD2dM3ZStc",
    "AIzaSyCuKxOa7GoY6id_aG-C3_uhvfJ1iI0SeQ0",
    "AIzaSyBwASUXeAVJ6xFFZdfjNZO5Hsumr4KAntw",
    "AIzaSyB4EZanzOFSu589lfBVO3M8dy72fBW2ObY",
    "AIzaSyASbyRix7Cbae7qCgPQntshA5DVJSVJbo4",
    "AIzaSyD07UM2S3qdSUyyY0Hp4YtN04J60PcO41w",
    "AIzaSyA9037TcPXJ2tdSrEe-hzLCn0Xa5zjiUOo",
]
WHATSAPP_TOKEN = "EAARw2Bvip3MBPOv7lmh95XKvSPwiqO9mbYvNGBkY09joY37z7Q7yZBOWnUG2ZC0JGwMuQR5ZA0NzE8o9oXuNFDsZCdJ8mxA9mrCMHQCzhRmzcgV4zwVg01S8zbiWZARkG4py5SL6if1MvZBuRJkQNilImdXlyMFkxAmD3Ten7LUdw1ZAglxzeYLp5CCjbA9XTb4KAZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
AI_MODEL_NAME = "gemini-1.5-flash" # Usei o 1.5 Flash, que é ótimo com imagens e mais recente.

# --- PROJECT SETUP ---
app = Flask(__name__)
BASE_DIR = Path(__file__).parent
USER_DATA_DIR = BASE_DIR / "user_data"
USER_DATA_DIR.mkdir(exist_ok=True)
user_sessions = {}
processed_message_ids = set()

# --- CONSTANTS ---
CUSTOM_SEARCH_URL_BASE = "https://www.bing.com"
CUSTOM_SEARCH_URL_TEMPLATE = "https://www.bing.com/search?q=%s"
# A dimensão da janela do navegador que a IA vai ver.
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800

# --- SYSTEM PROMPT (TOTALMENTE REESCRITO) ---
SYSTEM_PROMPT = f""
You are "Magic Agent," a highly autonomous AI expert at controlling a web browser. You see the screen and issue commands to operate it.

--- YOUR CORE MECHANISM: THE VIRTUAL CURSOR ---

You operate by controlling a **virtual cursor**, which appears as a **red dot** on the screenshot you receive. Your primary interaction method is a two-step process:

1.  **MOVE:** First, you decide where you want to click or interact. You issue the `MOVE_CURSOR` command with the precise (x, y) coordinates. The top-left corner of the screen is (0, 0) and the bottom-right is ({VIEWPORT_WIDTH}, {VIEWPORT_HEIGHT}). On your next turn, you will see a new screenshot with the red dot at the location you specified.
2.  **ACT:** After you have confirmed the red dot is in the correct position, you issue an action command like `CLICK` or `CLEAR`. This action will happen exactly where the red dot is.

This two-step process is mandatory for precision. ALWAYS move the cursor first, then act.

--- ERROR RECOVERY ---
If a command failed, analyze the new screenshot and error message. Do not repeat the failed command. For example, if a `CLICK` did nothing, maybe you missed the target slightly. Use `MOVE_CURSOR` to adjust the position and try `CLICK` again.

--- GUIDING PRINCIPLES ---

1.  **PROACTIVE EXPLORATION & SCROLLING:** ALWAYS scroll down after a page loads or after an action to see the full content. The initial view is just the top of the page. Use the `SCROLL` command.

2.  **SEARCH STRATEGY:** To search the web, you MUST use the `CUSTOM_SEARCH` command with our "Bing" search engine. Do NOT use `NAVIGATE` to go to other search engines.

3.  **LOGIN & CREDENTIALS:** If a page requires a login, you MUST NOT attempt to fill it in. Stop and ask the user for permission using the `PAUSE_AND_ASK` command. Do the same for verification codes.

4.  **TYPING STRATEGY:** To type in a field, you must first `MOVE_CURSOR` to the text field, then `CLICK` to focus it, and only then use the `TYPE` command.

5.  **HANDLING OBSTACLES (CAPTCHA):** If you see a CAPTCHA, use `MOVE_CURSOR` and `CLICK` to try and solve it (e.g., clicking the "I'm not a robot" checkbox). If it's a complex "select all images" CAPTCHA, you cannot solve it. Use `GO_BACK` and choose a different path.

--- YOUR RESPONSE FORMAT ---

Your response MUST ALWAYS be a single JSON object with "command", "params", "thought", and "speak" fields.

--- COMMAND REFERENCE ---

**== CURSOR & INTERACTION COMMANDS ==**

1.  **`MOVE_CURSOR`**: Moves the virtual cursor (red dot) to a specific coordinate. THIS IS YOUR PRIMARY WAY OF AIMING.
    - **Params:** `{{"x": <int>, "y": <int>}}`
    - **Example:** `{{"command": "MOVE_CURSOR", "params": {{"x": 430, "y": 512}}, "thought": "I need to click the 'Login' button. I will first move my cursor over it to ensure I have the right coordinates.", "speak": "Estou movendo meu cursor para o botão de login."}}`

2.  **`CLICK`**: Performs a REAL mouse click at the current location of the virtual cursor. You MUST have moved the cursor first.
    - **Params:** `{}`
    - **Example:** `{{"command": "CLICK", "params": {{}}, "thought": "The red dot is perfectly on the 'Login' button. I will now click.", "speak": "Clicando agora."}}`

3.  **`TYPE`**: Types text into the currently focused element. You MUST `CLICK` an input field first.
    - **Params:** `{{"text": "<text_to_type>", "enter": <true/false>}}`

4.  **`CLEAR`**: Clears text from the input field located under the virtual cursor.
    - **Params:** `{}`
    - **Example:** `{{"command": "CLEAR", "params": {{}}, "thought": "The cursor is on the search bar which has old text. I'll clear it before typing.", "speak": "Limpando o campo de busca."}}`

5.  **`SCROLL`**: Scrolls the page up or down.
    - **Params:** `{{"direction": "<up|down>"}}`

**== BROWSER & NAVIGATION COMMANDS ==**

6.  **`START_BROWSER`**: Initiates a new browser session.
    - **Params:** `{}`

7.  **`NAVIGATE`**: Goes directly to a URL.
    - **Params:** `{{"url": "<full_url>"}}`

8.  **`CUSTOM_SEARCH`**: Performs a search using "Bing".
    - **Params:** `{{"query": "<search_term>"}}`

9.  **`GO_BACK`**: Navigates to the previous page in history.
    - **Params:** `{}`

10. **`END_BROWSER`**: Closes the browser when the task is fully complete.
    - **Params:** `{{"reason": "<summary>"}}`

**== USER INTERACTION COMMANDS ==**

11. **`PAUSE_AND_ASK`**: Pauses to ask the user a question.
    - **Params:** `{{"question": "<your_question>"}}`

12. **`SPEAK`**: For simple conversation.
    - **Params:** `{{"text": "<your_response>"}}`

--- LANGUAGE & CONTEXT ---

- You must speak the same language as the user.
- You are an AI called "Magic Agent", built by Pyxel (pyxelworld.com). You are an expert at browsing. For other tasks (like generating images, writing long texts), tell the user to talk to the main AI, "Magic", at https://wa.me/551127375623 or https://askmagic.com.br. You can create pre-filled links for the user, for example: `https://wa.me/551127375623?text=gere+uma+imagem+de+um+gato`.

REMEMBER: ONLY THE "speak" FIELD IS SENT TO THE USER! Your "thought" is for your internal monologue.
""

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
    """Uploads an image and sends it to the user."""
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
    if not media_id:
        print("Failed to get media ID from WhatsApp upload.")
        return
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
            "user_dir": user_dir, "tab_handles": {}, "is_processing": False,
            "stop_requested": False, "interrupt_requested": False,
            # A posição do cursor começa no centro da tela.
            "cursor_pos": (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2)
        }
        user_dir.mkdir(parents=True, exist_ok=True)
        user_sessions[phone_number] = session
    return user_sessions[phone_number]

def start_browser(session):
    if session.get("driver"): return session["driver"]
    print("Starting new browser instance...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}")
    options.add_argument(f"--user-data-dir={session['user_dir'] / 'profile'}")
    try:
        driver = webdriver.Chrome(options=options)
        session["driver"] = driver; session["mode"] = "BROWSER"
        return driver
    except Exception as e:
        print(f"CRITICAL: Error starting Selenium browser: {e}")
        traceback.print_exc()
        return None

def close_browser(session):
    if session.get("driver"):
        print(f"Closing browser for session {session['user_dir'].name}")
        try: session["driver"].quit()
        except: pass
        session["driver"] = None
    session["mode"] = "CHAT"; session["original_prompt"] = ""; session["tab_handles"] = {}
    session["cursor_pos"] = (VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2)

def get_page_state(driver, session):
    screenshot_path = session["user_dir"] / f"state_{int(time.time())}.png"
    
    # 1. Pega informações das abas
    try:
        window_handles = driver.window_handles
        current_handle = driver.current_window_handle
        tabs = []
        session["tab_handles"] = {}
        for i, handle in enumerate(window_handles):
            tab_id = i + 1
            session["tab_handles"][tab_id] = handle
            driver.switch_to.window(handle)
            tabs.append({"id": tab_id, "title": driver.title, "is_active": handle == current_handle})
        driver.switch_to.window(current_handle)
        tab_info_text = "Open Tabs:\n" + "".join([f"  Tab {t['id']}: {t['title'][:70]}{' (Current)' if t['is_active'] else ''}\n" for t in tabs])
    except Exception as e:
        print(f"Could not get tab info: {e}")
        return None, ""

    # 2. Tira a screenshot e desenha o cursor virtual
    try:
        png_data = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(png_data))
        draw = ImageDraw.Draw(image)

        # Pega a posição do cursor da sessão
        cursor_x, cursor_y = session['cursor_pos']
        
        # Desenha a bola do cursor (vermelha com borda branca para visibilidade)
        radius = 8
        outline_width = 2
        # Borda
        draw.ellipse([(cursor_x - radius, cursor_y - radius), 
                      (cursor_x + radius, cursor_y + radius)], 
                     fill='white', outline='white')
        # Centro
        draw.ellipse([(cursor_x - (radius - outline_width), cursor_y - (radius - outline_width)), 
                      (cursor_x + (radius - outline_width), cursor_y + (radius - outline_width))], 
                     fill='red', outline='red')
        
        image.save(screenshot_path)
        print(f"State captured with cursor at {session['cursor_pos']}.")
        return screenshot_path, tab_info_text
    except Exception as e:
        print(f"Error getting page state or drawing cursor: {e}")
        traceback.print_exc()
        return None, tab_info_text

def call_ai(chat_history, context_text="", image_path=None):
    prompt_parts = [context_text]
    if image_path:
        try:
            img = Image.open(image_path)
            prompt_parts.append(img)
        except Exception as e:
            return json.dumps({"command": "END_BROWSER", "params": {"reason": f"Error: {e}"}, "thought": "Image read failed.", "speak": "Erro com a visualização da tela."})
    
    last_error = None
    for i, key in enumerate(GEMINI_API_KEYS):
        try:
            print(f"Attempting to call AI with API key #{i+1}...")
            genai.configure(api_key=key)
            model = genai.GenerativeModel(AI_MODEL_NAME, system_instruction=SYSTEM_PROMPT)
            # A API do Gemini 1.5 Flash espera um formato de histórico ligeiramente diferente
            # e não usa `start_chat` da mesma forma para multimodal.
            # Vamos construir o histórico manualmente para o `generate_content`.
            history_for_api = []
            for item in chat_history:
                # O gemini espera 'parts' como uma lista. O nosso já está assim.
                history_for_api.append({'role': item['role'], 'parts': item['parts']})

            response = model.generate_content(
                contents=[*history_for_api, {'role': 'user', 'parts': prompt_parts}],
                generation_config={"response_mime_type": "application/json"}
            )
            print("AI call successful.")
            return response.text
        except Exception as e:
            print(f"API key #{i+1} failed. Error: {e}")
            last_error = e
            continue
            
    print("All API keys failed.")
    return json.dumps({"command": "END_BROWSER", "params": {"reason": f"AI error: {last_error}"}, "thought": "AI API failed.", "speak": "Erro ao conectar com meu cérebro."})

def process_next_browser_step(from_number, session, caption):
    screenshot_path, tab_info_text = get_page_state(session["driver"], session)
    if screenshot_path:
        context_text = f"User's Goal: {session['original_prompt']}\n\n{tab_info_text}\n{caption}"
        send_whatsapp_image(from_number, screenshot_path, caption=caption)
        ai_response = call_ai(session["chat_history"], context_text=context_text, image_path=screenshot_path)
        process_ai_command(from_number, ai_response)
    else:
        send_whatsapp_message(from_number, "[Sistema] Não foi possível ver o navegador, fechando...")
        close_browser(session)

def process_ai_command(from_number, ai_response_text):
    session = get_or_create_session(from_number)
    
    if session.get("stop_requested"):
        print("Stop was requested, ignoring AI command.")
        session["stop_requested"] = False
        session["chat_history"] = []
        return
    if session.get("interrupt_requested"):
        print("Interrupt was requested, ignoring AI command.")
        session["interrupt_requested"] = False
        return

    try:
        command_data = json.loads(ai_response_text)
    except json.JSONDecodeError:
        send_whatsapp_message(from_number, f"[Sistema] A IA respondeu em um formato inválido. Resposta completa:\n\n{ai_response_text}")
        if session["mode"] == "BROWSER":
            # Não fecha, apenas pede para o usuário guiar.
            session["is_processing"] = False 
            send_whatsapp_message(from_number, "[Sistema] A IA está confusa. Por favor, me diga o que fazer a seguir.")
        return
        
    command = command_data.get("command")
    params = command_data.get("params", {})
    thought = command_data.get("thought", "")
    speak = command_data.get("speak", "")
    
    print(f"Executing: {command} | Params: {params} | Thought: {thought}")
    session["chat_history"].append({"role": "model", "parts": [ai_response_text]})
    if speak:
        send_whatsapp_message(from_number, speak)
    
    driver = session.get("driver")
    
    if not driver and command not in ["SPEAK", "START_BROWSER", "END_BROWSER", "PAUSE_AND_ASK"]:
        send_whatsapp_message(from_number, "[Sistema] O navegador não está aberto. Abrindo e tentando o comando novamente...")
        driver = start_browser(session)
        if not driver:
            send_whatsapp_message(from_number, "[Sistema] Falha crítica ao iniciar o navegador. A tarefa foi encerrada.")
            close_browser(session)
            return
        time.sleep(1)
        # Re-processa o mesmo comando agora que o navegador está aberto
        process_ai_command(from_number, ai_response_text)
        return

    try:
        # Ação foi feita no navegador? Se não (ex: MOVE_CURSOR), não esperamos 2s.
        action_in_browser = True 

        if command == "MOVE_CURSOR":
            x = params.get("x", 0)
            y = params.get("y", 0)
            session['cursor_pos'] = (x, y)
            print(f"Cursor position updated to ({x}, {y}).")
            # Mover o cursor não é uma ação no navegador, é só uma atualização de estado
            # que será refletida na próxima screenshot.
            action_in_browser = False 
        
        elif command == "CLICK":
            x, y = session['cursor_pos']
            print(f"Performing REAL click at cursor position ({x}, {y})")
            # Usamos ActionChains para um clique real nas coordenadas do viewport
            action = ActionChains(driver)
            # move_to_element_with_offset(body, x, y) é a forma mais confiável
            body = driver.find_element(By.TAG_NAME, 'body')
            action.move_to_element_with_offset(body, x, y).click().perform()

        elif command == "TYPE":
            text_to_type = params.get("text", "")
            # O ideal é que a IA já tenha focado o campo com um CLICK
            ActionChains(driver).send_keys(text_to_type).perform()
            if params.get("enter"):
                ActionChains(driver).send_keys(Keys.ENTER).perform()

        elif command == "CLEAR":
            x, y = session['cursor_pos']
            print(f"Clearing element at cursor position ({x}, {y})")
            # Para limpar, focamos no elemento e então enviamos CTRL+A e DELETE
            try:
                action = ActionChains(driver)
                body = driver.find_element(By.TAG_NAME, 'body')
                # Move, clica para focar, envia as teclas
                action.move_to_element_with_offset(body, x, y).click().send_keys(Keys.CONTROL + "a").send_keys(Keys.DELETE).perform()
            except Exception as e:
                print(f"Could not clear element with ActionChains, trying JS fallback. Error: {e}")
                driver.execute_script("document.elementFromPoint(arguments[0], arguments[1]).value = '';", x, y)

        elif command == "START_BROWSER":
            driver = start_browser(session)
            if not driver:
                send_whatsapp_message(from_number, "[Sistema] Houve um erro ao abrir o navegador.")
                close_browser(session)
                return
            time.sleep(1)
            driver.get(CUSTOM_SEARCH_URL_BASE)

        elif command == "NAVIGATE": driver.get(params.get("url", CUSTOM_SEARCH_URL_BASE))
        elif command == "CUSTOM_SEARCH": driver.get(CUSTOM_SEARCH_URL_TEMPLATE % quote_plus(params.get('query', '')))
        elif command == "GO_BACK": driver.back()
        elif command == "SCROLL": driver.execute_script(f"window.scrollBy(0, {VIEWPORT_HEIGHT * 0.8 if params.get('direction', 'down') == 'down' else -VIEWPORT_HEIGHT * 0.8});")
        elif command == "END_BROWSER":
            send_whatsapp_message(from_number, f"*Tarefa Concluída.*\n*Sumário:* {params.get('reason', 'Nenhum sumário fornecido.')}")
            close_browser(session)
            return
        elif command == "PAUSE_AND_ASK" or command == "SPEAK":
            # Esses comandos não interagem com o navegador, apenas pausam o loop
            session["is_processing"] = False # Libera para o usuário responder
            return
        else:
            print(f"Unknown command: {command}")
            send_whatsapp_message(from_number, f"[Sistema] A IA tentou usar um comando desconhecido: {command}")
            action_in_browser = False
        
        # Espera um pouco para a página carregar após uma ação
        if action_in_browser:
            time.sleep(2)
        
        # Sempre processa o próximo passo para mostrar o resultado da ação
        process_next_browser_step(from_number, session, f"[Sistema] O Agent executou a ação: {command}")

    except Exception as e:
        error_summary = f"Error during command '{command}': {e}"
        print(f"CRITICAL: {error_summary}"); traceback.print_exc()
        send_whatsapp_message(from_number, "[Sistema] Ocorreu um erro. Tentando novamente com a ajuda da IA...")
        time.sleep(1)
        # Em caso de erro, mostre o estado atual e peça para a IA corrigir
        process_next_browser_step(from_number, session, caption=f"An error occurred: {error_summary}. What should I do now?")

# --- O restante do código do Flask para o Webhook permanece o mesmo ---

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
                print(f"Duplicate message ID {message_id} received. Ignoring."); return Response(status=200)
            processed_message_ids.add(message_id)
            
            if message_info.get("type") != "text":
                send_whatsapp_message(message_info.get("from"), "[Sistema] O Agent apenas suporta mensagens de texto no momento."); return Response(status=200)

            from_number, user_message_text = message_info["from"], message_info["text"]["body"]
            print(f"Received from {from_number}: '{user_message_text}'")
            session = get_or_create_session(from_number)
            
            command_text = user_message_text.strip().lower()
            if command_text == "/stop":
                print(f"User {from_number} issued /stop command.")
                session["stop_requested"] = True
                close_browser(session)
                session["is_processing"] = False
                send_whatsapp_message(from_number, "[Sistema] Ação cancelada e sessão encerrada.")
                return Response(status=200)

            if command_text == "/interrupt":
                print(f"User {from_number} issued /interrupt command.")
                if session["mode"] != "BROWSER":
                    send_whatsapp_message(from_number, "[Sistema] Nenhuma ação em andamento para interromper.")
                else:
                    session["interrupt_requested"] = True
                    session["is_processing"] = False # Allow new user input
                    send_whatsapp_message(from_number, "[Sistema] Ação interrompida. Sua próxima mensagem será enviada à IA para que ela saiba como continuar.")
                return Response(status=200)

            if command_text == "/clear":
                print(f"User {from_number} issued /clear command.")
                close_browser(session)
                if from_number in user_sessions:
                    del user_sessions[from_number]
                send_whatsapp_message(from_number, "[Sistema] Memória do Agent e sessão do navegador foram limpas.")
                print(f"Session for {from_number} cleared.")
                return Response(status=200)

            if session.get("is_processing"):
                send_whatsapp_message(from_number, "[Sistema] O Agent ainda está trabalhando. Envie /interrupt para interrompê-lo e dar novas instruções, ou /stop para encerrar a tarefa."); return Response(status=200)
            
            try:
                session["is_processing"] = True
                session["chat_history"].append({"role": "user", "parts": [user_message_text]})

                if session["mode"] == "CHAT":
                    session["original_prompt"] = user_message_text
                    ai_response = call_ai(session["chat_history"], context_text=f"A new task has started. The user wants me to: {user_message_text}")
                    process_ai_command(from_number, ai_response)
                elif session["mode"] == "BROWSER":
                    # O usuário está respondendo a uma pergunta ou dando uma instrução no meio da tarefa
                    process_next_browser_step(from_number, session, f"[User Guidance]: {user_message_text}")
            finally:
                # Libera o processamento se não for uma pausa intencional
                if not session.get("interrupt_requested") and command_data.get("command") not in ["PAUSE_AND_ASK", "SPEAK"]:
                    session["is_processing"] = False

        except (KeyError, IndexError, TypeError) as e:
            # Silencia erros comuns do webhook se a mensagem não for do tipo esperado
            pass 
        except Exception as e:
            print(f"Error processing webhook: {e}")
            traceback.print_exc()
        return Response(status=200)

if __name__ == '__main__':
    print("--- Magic Agent WhatsApp Bot Server (Cursor Mode) ---")
    app.name = 'whatsapp'
    # Use 0.0.0.0 para ser acessível na sua rede local, se necessário
    app.run(host='0.0.0.0', port=5000, debug=False)
