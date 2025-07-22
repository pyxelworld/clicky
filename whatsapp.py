import os
import json
import requests
from flask import Flask, request, Response
from google import genai
from google.genai import types

GEMINI_API_KEY = "AIzaSyA3lDQ2Um5-2q7TJdruo2hNpjflYR9U4LU"
WHATSAPP_TOKEN = "EAARw2Bvip3MBPBJBZBWZCTvjyafC4y1a3X0dttPlqRWOV7PW364uLYBrih7aGDC8RiGyDpBd0MkHlxZAGK9BKiJKhs2V8GZCE7kOjk3cbCV8VJX9y655qpqQqZAZA418a0SoHcCeaxLgrIoxm0xZBqxjf9nWGMzuyLSCjHYVyVcl6g6idMe9xjrFnsf4PNqZCEoASwZDZD"
WHATSAPP_PHONE_NUMBER_ID = "757771334076445" # Observação: IDs de número de telefone costumam ser mais longos. Se tiver problemas, confirme este valor no painel da Meta.
VERIFY_TOKEN = "121222220611" # Este token é usado para verificar a identidade do seu webhook

# Configuração do Flask
app = Flask(__name__)

def call_gemini(user_message: str) -> str:
    try:
        # 1. Cria o cliente, exatamente como no seu exemplo.
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 2. Define o modelo a ser usado.
        model_name = "gemini-2.0-flash" # Modelo moderno e eficiente

        # 3. Prepara o conteúdo da mensagem do usuário na estrutura correta.
        # A mensagem do usuário é inserida aqui.
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_message),
                ],
            ),
        ]
        
        # 4. Define a configuração de geração, incluindo a instrução de sistema.
        # A instrução de sistema define a personalidade do bot.
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text="Você é um assistente prestativo chamado ClickyBot. Responda de forma concisa e amigável."),
            ],
        )

        # 5. Chama o método de streaming e coleta os pedaços (chunks) da resposta.
        # Como o WhatsApp não suporta streaming, juntamos tudo em uma única string.
        response_chunks = []
        for chunk in client.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=generate_content_config,
        ):
            response_chunks.append(chunk.text)
            
        # 6. Retorna a resposta completa.
        return "".join(response_chunks)

    except Exception as e:
        print(f"Erro ao chamar a API do Gemini: {e}")
        return "Desculpe, ocorreu um erro ao tentar processar sua mensagem. Tente novamente mais tarde."

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
                    
                    # Chama a função Gemini corrigida
                    gemini_response = call_gemini(user_message_text)
                    
                    # Envia a resposta de volta
                    send_whatsapp_message(from_number, gemini_response)
                
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
