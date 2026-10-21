from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE CREDENCIALES Y ENDPOINTS
# ==========================================
WEBEX_BOT_TOKEN = "NTI2NGQ3ZTAtMjUxYS00MjA0LThlY2YtMDYwNTA4NGI0YTFmMjY2ZTk4OTItZDIz_PF84_73fcfd80-321c-49b4-9377-d25cd201dbf6"
BMC_URL = "https://portaltiarcor-dev-is.onbmc.com/api/com.bmc.dsom.hgm/channels/AGGD3RELFXP86ATL5ET2TL5ET25NZ2/generic"

# Identidad del Bot (se obtiene automáticamente al iniciar)
BOT_PERSON_ID = None
BOT_EMAIL = None

def inicializar_bot():
    """Consulta la API de Webex para obtener el ID y email exactos del Bot."""
    global BOT_PERSON_ID, BOT_EMAIL
    try:
        res = requests.get(
            "https://webexapis.com/v1/people/me",
            headers={"Authorization": f"Bearer {WEBEX_BOT_TOKEN}"},
            timeout=10
        )
        if res.status_code == 200:
            datos = res.json()
            BOT_PERSON_ID = datos.get("id")
            BOT_EMAIL = datos.get("emails", [None]) if datos.get("emails") else None
            print(f"🤖 Bot Identificado con éxito -> ID: {BOT_PERSON_ID} | Email: {BOT_EMAIL}")
        else:
            print(f"⚠️ No se pudo obtener la identidad del Bot ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"⚠️ Error al inicializar identidad del bot: {e}")

# Ejecutar la consulta de identidad del Bot al arrancar
inicializar_bot()


# ==========================================
# ENDPOINT 1: ENTRADA (Desde Webex hacia BMC)
# ==========================================
@app.route('/webex-webhook', methods=['POST'])
def webex_webhook():
    payload = request.get_json() or {}
    data = payload.get('data', {})
    
    actor_id = payload.get('actorId')
    person_id = data.get('personId')
    person_email = data.get('personEmail', '')

    # 1. Filtro Anti-Loop Primario (Verifica ID del Bot y Dominio @webex.bot)
    if (BOT_PERSON_ID and (actor_id == BOT_PERSON_ID or person_id == BOT_PERSON_ID)) or \
       (BOT_EMAIL and person_email == BOT_EMAIL) or \
       person_email.endswith(('@webex.bot', '@sparkbot.io')):
        print("🤖 Mensaje generado por el Bot detectado. Ignorando evento.")
        return jsonify({"status": "ignored_bot_message"}), 200

    message_id = data.get('id')
    room_id = data.get('roomId')

    if not message_id:
        return jsonify({"status": "ignored_no_id"}), 200

    # 2. Consultar el contenido del mensaje a la API de Webex
    headers_webex = {"Authorization": f"Bearer {WEBEX_BOT_TOKEN}"}
    res_webex = requests.get(f"https://webexapis.com/v1/messages/{message_id}", headers=headers_webex, timeout=10)

    if res_webex.status_code != 200:
        print("❌ Error consultando el mensaje en Webex:", res_webex.text)
        return jsonify({"error": "Falló consulta a Webex"}), 500

    msg_json = res_webex.json()
    message_text = msg_json.get('text', '')
    sender_email = msg_json.get('personEmail', person_email)
    sender_person_id = msg_json.get('personId')

    # 3. Filtro Anti-Loop Secundario (Verifica remitente real del mensaje recuperado)
    if (BOT_PERSON_ID and sender_person_id == BOT_PERSON_ID) or \
       (BOT_EMAIL and sender_email == BOT_EMAIL) or \
       sender_email.endswith(('@webex.bot', '@sparkbot.io')):
        print("🤖 El mensaje recuperado de Webex fue enviado por el Bot. Ignorando.")
        return jsonify({"status": "ignored_bot_message"}), 200

    # Ignorar mensajes de confirmación de estado o vacíos
    if '{"statusCode": 200}' in message_text or message_text.strip() == '':
        print(f"⚠️ Mensaje con formato de estado o vacío ignorado: '{message_text}'")
        return jsonify({"status": "ignored_invalid_text"}), 200

    print(f"📩 Mensaje válido del usuario ({sender_email}): '{message_text}'")

    # 4. Reenviar la consulta a BMC HelixGPT
    bmc_payload = {
        "event_type": "message",
        "created": msg_json.get("created"),
        "data": {
            "id": message_id,
            "roomId": room_id,
            "personId": sender_person_id,
            "personEmail": sender_email,
            "text": message_text
        }
    }
    
    headers_bmc = {"Content-Type": "application/json"}
    res_bmc = requests.post(BMC_URL, json=bmc_payload, headers=headers_bmc, timeout=10)

    print(f"🚀 Confirmación de recepción de BMC ({res_bmc.status_code}): {res_bmc.text}")

    return jsonify({"status": "forwarded_to_bmc"}), 200


# ==========================================
# ENDPOINT 2: SALIDA (Desde BMC hacia Webex)
# ==========================================
@app.route('/bmc-response', methods=['POST'])
def bmc_response():
    payload = request.get_json() or {}
    print("📩 Petición recibida de BMC HelixGPT:", payload)

    respuesta_texto = payload.get('text') or payload.get('message')
    room_id = payload.get('roomId') or payload.get('conversationId') or payload.get('channelId')

    # Si la respuesta de BMC es un ACK de estado ("{"statusCode": 200}"), no enviarla a Webex
    if respuesta_texto:
        str_texto = str(respuesta_texto).strip()
        if 'statusCode' in str_texto or str_texto == '{"statusCode": 200}':
            print(f"⚠️ BMC envió una confirmación de estado ('{str_texto}'). No se publica en el chat.")
            return jsonify({"status": "ignored_status_ack"}), 200

    if respuesta_texto and room_id:
        headers_webex = {
            "Authorization": f"Bearer {WEBEX_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        payload_webex = {
            "roomId": room_id,
            "text": respuesta_texto
        }
        
        res_send = requests.post("https://webexapis.com/v1/messages", headers=headers_webex, json=payload_webex, timeout=10)
        print(f"📤 Mensaje del agente enviado a Webex ({res_send.status_code}): {res_send.text}")
    else:
        print("⚠️ No se encontró 'text' o 'roomId' válido en el payload de BMC.")

    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
