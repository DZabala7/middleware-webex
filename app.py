from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE CREDENCIALES Y ENDPOINTS
# ==========================================
# Token de acceso de tu Bot de Cisco Webex
WEBEX_BOT_TOKEN = "NTI2NGQ3ZTAtMjUxYS00MjA0LThlY2YtMDYwNTA4NGI0YTFmMjY2ZTk4OTItZDIz_PF84_73fcfd80-321c-49b4-9377-d25cd201dbf6"

# URL del canal Custom Webhook en BMC HelixGPT
BMC_URL = "https://portaltiarcor-dev-is.onbmc.com/api/com.bmc.dsom.hgm/channels/AGGD3RELFXP86ATL5ET2TL5ET25NZ2/generic"

# ==========================================
# ENDPOINT 1: ENTRADA (Desde Webex hacia BMC)
# ==========================================
@app.route('/webex-webhook', methods=['POST'])
def webex_webhook():
    payload = request.get_json() or {}
    data = payload.get('data', {})
    
    message_id = data.get('id')
    person_email = data.get('personEmail', '')
    room_id = data.get('roomId')

    # 1. Filtro Anti-Loop: Ignorar mensajes enviados por cuentas de Bots
    if person_email.endswith('@webex.bot'):
        return jsonify({"status": "ignored_bot_message"}), 200

    if not message_id:
        return jsonify({"status": "ignored_no_id"}), 200

    # 2. Paso A: Consultar el texto del mensaje a la API de Webex
    headers_webex = {"Authorization": f"Bearer {WEBEX_BOT_TOKEN}"}
    res_webex = requests.get(f"https://webexapis.com/v1/messages/{message_id}", headers=headers_webex)

    if res_webex.status_code != 200:
        print("❌ Error consultando el mensaje en Webex:", res_webex.text)
        return jsonify({"error": "Falló consulta a Webex"}), 500

    msg_json = res_webex.json()
    message_text = msg_json.get('text', '')
    sender_email = msg_json.get('personEmail', person_email)

    # Verificación secundaria Anti-Loop
    if sender_email.endswith('@webex.bot'):
        return jsonify({"status": "ignored_bot_message"}), 200

    print(f"📩 Mensaje del usuario ({sender_email}): '{message_text}'")

    # 3. Paso B: Reenviar la consulta a BMC HelixGPT
    bmc_payload = {
        "event_type": "message",
        "created": msg_json.get("created"),
        "data": {
            "id": message_id,
            "roomId": room_id,
            "personId": msg_json.get("personId"),
            "personEmail": sender_email,
            "text": message_text
        }
    }
    
    headers_bmc = {"Content-Type": "application/json"}
    res_bmc = requests.post(BMC_URL, json=bmc_payload, headers=headers_bmc)

    print(f"🚀 Confirmación de recepción de BMC ({res_bmc.status_code}): {res_bmc.text}")

    # Simplemente confirmamos a Webex que recibimos el webhook (no enviamos texto al chat todavía)
    return jsonify({"status": "forwarded_to_bmc"}), 200

# ==========================================
# ENDPOINT 2: SALIDA (Desde BMC hacia Webex)
# ==========================================
@app.route('/bmc-response', methods=['POST'])
def bmc_response():
    payload = request.get_json() or {}
    print("📩 Respuesta asíncrona recibida de BMC HelixGPT:", payload)

    # Mapeo según el Outgoing Payload Mapping de BMC ("text" y "roomId")
    respuesta_texto = payload.get('text') or payload.get('message')
    room_id = payload.get('roomId') or payload.get('conversationId') or payload.get('channelId')

    if respuesta_texto and room_id:
        headers_webex = {
            "Authorization": f"Bearer {WEBEX_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        payload_webex = {
            "roomId": room_id,
            "text": respuesta_texto
        }
        
        # Publicar el mensaje del agente de BMC en el chat de Cisco Webex
        res_send = requests.post("https://webexapis.com/v1/messages", headers=headers_webex, json=payload_webex)
        print(f"📤 Mensaje enviado a Webex ({res_send.status_code}): {res_send.text}")
    else:
        print("⚠️ No se encontró 'text' o 'roomId' en el payload de BMC:", payload)

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
