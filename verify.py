# Arquivo: verify_webhook.py
# Este script serve APENAS para o primeiro passo de verificação do Webhook da Meta.

from flask import Flask, request, Response

app = Flask(__name__)

# O seu token de verificação, conforme solicitado.
VERIFY_TOKEN = "12122222061" 

@app.route('/webhook', methods=['GET'])
def webhook_verification():
    """
    Esta rota lida com a verificação do webhook pela Meta.
    Ela verifica se o token e o modo estão corretos e responde
    com o 'challenge' para confirmar a autenticidade do seu endpoint.
    """
    print("Recebida requisição de verificação de webhook...")
    
    # Extrai os parâmetros da requisição GET
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    # Verifica se o modo é 'subscribe' e o token corresponde ao seu
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print(f"Webhook verificado com sucesso! Respondendo com o challenge: {challenge}")
        return Response(challenge, status=200)
    else:
        # Se a verificação falhar, retorna um erro 403 (Proibido)
        print("Falha na verificação do Webhook. Tokens não correspondem.")
        return Response(status=403)

if __name__ == '__main__':
    # Roda o servidor na porta 5000. Use ngrok para expor esta porta.
    print("Servidor de verificação iniciado em http://localhost:5000")
    print("Use este servidor APENAS para o passo de verificação no painel da Meta.")
    app.run(port=5000, debug=True)
