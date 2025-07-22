# Arquivo: bot_whatsapp.py
# Este é o bot principal que responde às mensagens do WhatsApp.

import os
import json
import requests
from flask import Flask, request, Response
from google import genai
from google.genai import types

# --- INÍCIO DAS CONFIGURAÇÕES E CHAVES ---
# ATENÇÃO: É uma má prática de segurança colocar chaves diretamente no código.
# O ideal é usar variáveis de ambiente. Faça isso após seus testes.

# Chave da API do Google Gemini
GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"

# Credenciais da API do WhatsApp (Meta)
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445" # Observação: IDs de número de telefone costumam ser mais longos. Se tiver problemas, confirme este valor no painel da Meta.
VERIFY_TOKEN = "12122222061" # Este token é usado para verificar a identidade do seu webhook

# --- FIM DAS CONFIGURAÇÕES E CHAVES ---

# Configuração do Flask
app = Flask(__name__)

# Configura o cliente da Google GenAI
genai.configure(api_key=GEMINI_API_KEY)

def call_gemini(user_message: str) -> str:
    """Função que chama a API do Gemini e retorna a resposta."""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(user_message)
        return response.text
    except Exception as e:
        print(f"Erro ao chamar a API do Gemini: {e}")
        return "Desculpe, ocorreu um erro ao tentar processar sua mensagem."

def send_whatsapp_message(to_number: str, message: str):
    """Envia uma mensagem de texto para um número de WhatsApp usando a API da Meta."""
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

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    # A verificação GET é necessária para a configuração inicial do webhook.
    # O bot principal também precisa ter essa rota para o caso de a Meta
    # tentar verificar novamente no futuro.
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return Response(challenge, status=200)
        else:
            return Response(status=403)

    # Rota POST para receber as mensagens do usuário
    if request.method == 'POST':
        body = request.get_json()
        print(json.dumps(body, indent=2)) # Log para depuração

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
                    
                    gemini_response = call_gemini(user_message_text)
                    send_whatsapp_message(from_number, gemini_response)
                
                else:
                    non_text_message = "Desculpe, só entendo mensagens de texto por enquanto."
                    print(f"Mensagem não-texto ({message_type}) recebida de {from_number}.")
                    send_whatsapp_message(from_number, non_text_message)

        except (KeyError, IndexError, TypeError):
            pass

        return Response(status=200)

if __name__ == '__main__':
    print("Servidor do Bot WhatsApp iniciado em http://localhost:5000")
    print("Aguardando mensagens...")
    app.run(port=5000, debug=True)
