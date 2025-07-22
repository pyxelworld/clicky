import os
import json
import requests
import re
import base64
import uuid
from flask import Flask, request, Response, send_from_directory
from google import genai
from google.genai import types
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445"
VERIFY_TOKEN = "121222220611"
PUBLIC_URL = "https://your-cloudflared-url.trycloudflare.com"  # Replace with your actual Cloudflared tunnel URL

# Configuração do Flask
app = Flask(__name__)

# Global sessions
sessions = {}

SYSTEM_PROMPT = """
Você é o Magic Agent, um assistente de IA prestativo que pode controlar um navegador web para ajudar os usuários.
Responda de forma concisa e amigável. Fora do modo navegador, converse normalmente.

Para iniciar o navegador: Saia [ACTION: {"type": "start_browser", "url": "opcional_url"}] no final da sua resposta.

Quando o navegador estiver ativo, você receberá capturas de tela (imagens PNG de 1280x800 pixels). Analise a imagem e decida a próxima ação.
Coordenadas são do topo-esquerda (0,0) até (1280,800).
Output apenas UMA ação por resposta, no formato [ACTION: {json}].
Após a ação, você receberá uma nova captura de tela.

Comandos disponíveis:
- {"type": "click", "x": int, "y": int} - Clique nas coordenadas da captura de tela.
- {"type": "scroll", "direction": "down", "amount": 500} - Direction: up, down, left, right. Amount em pixels.
- {"type": "type", "text": "hello"} - Digite o texto no elemento focado (clique primeiro para focar).
- {"type": "press_key", "key": "ENTER"} ou "CONTROL+T" - Pressione tecla ou atalho.
- {"type": "open_tab", "url": "https://example.com"} - Abra nova aba e mude para ela.
- {"type": "switch_tab", "index": 0} - Mude para aba pelo índice (0 é a primeira).
- {"type": "close_tab"} - Feche a aba atual.
- {"type": "close_browser"} - Feche o navegador e termine a sessão.
- {"type": "ask_user", "question": "Qual é o seu email?"} - Pergunte ao usuário e pause para resposta.

Quando a tarefa estiver completa, output [ACTION: {"type": "close_browser"}] e sua resposta final ao usuário.
Se precisar de mais info, use ask_user.
Downloads vão para uma pasta do usuário.
"""

def call_gemini(history: list) -> str:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        model_name = "gemini-2.0-flash"
        contents = history
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
        return "".join(response_chunks)
    except Exception as e:
        print(f"Erro ao chamar a API do Gemini: {e}")
        return "Desculpe, ocorreu um erro ao tentar processar sua mensagem. Tente novamente mais tarde."

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
    if response.status_code == 200:
        print(f"Mensagem enviada para {to_number} com sucesso.")
    else:
        print(f"Falha ao enviar mensagem: {response.status_code} - {response.text}")

def send_whatsapp_image(to_number: str, image_link: str, caption: str = ""):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {"link": image_link, "caption": caption},
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Imagem enviada para {to_number} com sucesso.")
    else:
        print(f"Falha ao enviar imagem: {response.status_code} - {response.text}")

def parse_action(response: str):
    match = re.search(r'\[ACTION:\s*({.*?})\s*\]', response, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            return None
    return None

def save_screenshot(phone: str, base64_str: str):
    filename = f"{uuid.uuid4()}.png"
    path = f"screenshots/{phone}/{filename}"
    with open(path, "wb") as f:
        f.write(base64.b64decode(base64_str))
    return filename

def execute_browser_action(driver, action):
    type_ = action['type']
    if type_ == 'click':
        x = action['x']
        y = action['y']
        driver.execute_script("""
        var ev = new MouseEvent('click', {view: window, bubbles: true, cancelable: true, clientX: arguments[0], clientY: arguments[1]});
        var el = document.elementFromPoint(arguments[0], arguments[1]);
        if (el) el.dispatchEvent(ev);
        """, x, y)
        return f"clicando em ({x}, {y})"
    elif type_ == 'scroll':
        dir_ = action.get('direction', 'down')
        amount = action.get('amount', 100)
        if dir_ == 'down':
            driver.execute_script(f"window.scrollBy(0, {amount})")
        elif dir_ == 'up':
            driver.execute_script(f"window.scrollBy(0, -{amount})")
        elif dir_ == 'right':
            driver.execute_script(f"window.scrollBy({amount}, 0)")
        elif dir_ == 'left':
            driver.execute_script(f"window.scrollBy(-{amount}, 0)")
        return f"rolando {dir_} por {amount} pixels"
    elif type_ == 'type':
        text = action['text']
        ActionChains(driver).send_keys(text).perform()
        return f"digitou '{text}'"
    elif type_ == 'press_key':
        key = action['key']
        keys = key.split('+')
        ac = ActionChains(driver)
        for k in keys[:-1]:
            ac.key_down(getattr(Keys, k.upper()))
        ac.send_keys(keys[-1] if len(keys) == 1 else keys[-1].lower() if len(keys[-1]) == 1 else keys[-1])
        for k in reversed(keys[:-1]):
            ac.key_up(getattr(Keys, k.upper()))
        ac.perform()
        return f"pressionou tecla '{key}'"
    elif type_ == 'open_tab':
        url = action['url']
        driver.execute_script(f"window.open('{url}', '_blank')")
        driver.switch_to.window(driver.window_handles[-1])
        return f"abriu nova aba com {url}"
    elif type_ == 'switch_tab':
        index = action['index']
        if 0 <= index < len(driver.window_handles):
            driver.switch_to.window(driver.window_handles[index])
            return f"mudou para aba {index}"
        else:
            return "índice de aba inválido"
    elif type_ == 'close_tab':
        driver.close()
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
        return "fechou aba atual"
    return "Ação desconhecida"

def handle_action(phone: str, session, action):
    type_ = action['type']
    if type_ == 'start_browser':
        os.makedirs(f"chrome_profiles/{phone}", exist_ok=True)
        os.makedirs(f"downloads/{phone}", exist_ok=True)
        os.makedirs(f"screenshots/{phone}", exist_ok=True)
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,800")
        options.add_argument(f"user-data-dir={os.getcwd()}/chrome_profiles/{phone}")
        prefs = {"download.default_directory": f"{os.getcwd()}/downloads/{phone}"}
        options.add_experimental_option("prefs", prefs)
        session['driver'] = webdriver.Chrome(options=options)
        url = action.get('url', 'about:blank')
        session['driver'].get(url)
        session['browser_active'] = True
        return f"iniciando navegador em {url}"
    elif type_ == 'close_browser':
        return "fechando navegador"
    else:
        if not session.get('browser_active') or not session['driver']:
            return "Nenhum navegador ativo"
        return execute_browser_action(session['driver'], action)

def process_message(from_number: str, user_message_text: str):
    if from_number not in sessions:
        sessions[from_number] = {
            'history': [],
            'driver': None,
            'browser_active': False,
            'waiting_for_user': False,
            'last_screenshot': None,
        }
    session = sessions[from_number]

    # Append user message
    session['history'].append(types.Content(role="user", parts=[types.Part.from_text(text=user_message_text)]))

    if session['waiting_for_user']:
        session['waiting_for_user'] = False

    # Call Gemini
    response = call_gemini(session['history'])
    action = parse_action(response)

    if action:
        if action['type'] == 'ask_user':
            question = action.get('question', 'Pergunta não especificada')
            send_whatsapp_message(from_number, question)
            session['waiting_for_user'] = True
            session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
            return
        else:
            desc = handle_action(from_number, session, action)

            if session['browser_active']:
                screenshot_base64 = session['driver'].get_screenshot_as_base64()
                session['last_screenshot'] = screenshot_base64
                filename = save_screenshot(from_number, screenshot_base64)
                link = f"{PUBLIC_URL}/screenshots/{from_number}/{filename}"
                send_whatsapp_message(from_number, f"Magic Agent está {desc}...")
                send_whatsapp_image(from_number, link, "Captura de tela atual do navegador")
            else:
                send_whatsapp_message(from_number, f"Magic Agent: {desc}")

            if action['type'] == 'close_browser':
                if session['driver']:
                    session['driver'].quit()
                    session['driver'] = None
                session['browser_active'] = False
                text = re.sub(r'\[ACTION:\s*\{.*?\}\s*\]', '', response, flags=re.DOTALL | re.IGNORECASE).strip()
                if text:
                    send_whatsapp_message(from_number, text)
                session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
                return

            # Append AI response to history
            session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))

            if session['browser_active']:
                # Append new state to history
                new_user_content = types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=f"Ação realizada: {desc}. Novo estado do navegador:"),
                        types.Part.from_data(mime_type="image/png", data=base64.b64decode(session['last_screenshot'])),
                    ]
                )
                session['history'].append(new_user_content)

                # Enter loop for further actions
                max_steps = 20
                for step in range(max_steps):
                    response = call_gemini(session['history'])
                    action = parse_action(response)
                    if not action:
                        send_whatsapp_message(from_number, response)
                        if session['browser_active']:
                            session['driver'].quit()
                            session['driver'] = None
                            session['browser_active'] = False
                        session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
                        break
                    if action['type'] == 'ask_user':
                        question = action.get('question', 'Pergunta não especificada')
                        send_whatsapp_message(from_number, question)
                        session['waiting_for_user'] = True
                        session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
                        break
                    desc = handle_action(from_number, session, action)
                    screenshot_base64 = session['driver'].get_screenshot_as_base64()
                    session['last_screenshot'] = screenshot_base64
                    filename = save_screenshot(from_number, screenshot_base64)
                    link = f"{PUBLIC_URL}/screenshots/{from_number}/{filename}"
                    send_whatsapp_message(from_number, f"Magic Agent está {desc}...")
                    send_whatsapp_image(from_number, link, "Captura de tela atualizada")
                    if action['type'] == 'close_browser':
                        session['driver'].quit()
                        session['driver'] = None
                        session['browser_active'] = False
                        text = re.sub(r'\[ACTION:\s*\{.*?\}\s*\]', '', response, flags=re.DOTALL | re.IGNORECASE).strip()
                        if text:
                            send_whatsapp_message(from_number, text)
                        session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
                        break
                    # Append to history
                    session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))
                    new_user_content = types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=f"Ação realizada: {desc}. Novo estado do navegador:"),
                            types.Part.from_data(mime_type="image/png", data=base64.b64decode(screenshot_base64)),
                        ]
                    )
                    session['history'].append(new_user_content)
    else:
        send_whatsapp_message(from_number, response)
        session['history'].append(types.Content(role="model", parts=[types.Part.from_text(text=response)]))

@app.route('/screenshots/<phone>/<filename>')
def serve_screenshot(phone, filename):
    return send_from_directory(f'screenshots/{phone}', filename)

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
                
                if message_type == "text":
                    user_message_text = message_info["text"]["body"]
                    print(f"Mensagem de texto recebida de {from_number}: {user_message_text}")
                    
                    # Process the message
                    process_message(from_number, user_message_text)
                
                else:
                    non_text_message = "Desculpe, só entendo mensagens de texto por enquanto."
                    print(f"Mensagem não-texto ({message_type}) recebida de {from_number}.")
                    send_whatsapp_message(from_number, non_text_message)

        except (KeyError, IndexError, TypeError) as e:
            print(f"Erro no processamento do webhook: {e}")
            pass

        return Response(status=200)

if __name__ == '__main__':
    print("Servidor do Bot WhatsApp iniciado em http://localhost:5000")
    print("Aguardando mensagens via webhook...")
    app.run(port=5000, debug=False)
