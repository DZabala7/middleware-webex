from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# 1. Pega aquí el Token real de tu Bot de Webex
WEBEX_BOT_TOKEN = "TU_BOT_ACCESS_TOKEN_REAL"

# 2. URL de Webhook de BMC HelixGPT
BMC_URL = "https://portaltiarcor-is.onbmc.com/api/com.bmc.dsom.hgm/channels/AGGGYVF8D2202ATLVPT0TLVPT0JIG4/generic"

@app.route('/webex-webhook', methods=['POST'])
def webex_webhook():
    payload = request.get_json() or {}
    data = payload.get('data', {})
    
    message_id = data.get('id')
    person_email = data.get('personEmail')
    room_id = data.get('roomId')

    if not message_id:
        return jsonify({"status": "ignored"}), 200

    # Paso A: Consultar el texto del mensaje a la API de Webex
    headers_webex = {"Authorization": f"Bearer {WEBEX_BOT_TOKEN}"}
    res_webex = requests.get(f"https://webexapis.com/v1/messages/{message_id}", headers=headers_webex)

    if res_webex.status_code != 200:
        print("❌ Error consultando Webex:", res_webex.text)
        return jsonify({"error": "Falló consulta a Webex"}), 500

    msg_json = res_webex.json()
    message_text = msg_json.get('text', '')

    print(f"📩 Mensaje recibido de {person_email}: '{message_text}'")

    # Paso B: Reenviar el paquete completo con 'text' a BMC HelixGPT
    bmc_payload = {
        "personEmail": person_email,
        "text": message_text,
        "roomId": room_id
    }
    
    headers_bmc = {"Content-Type": "application/json"}
    
    # Petición POST a BMC HelixGPT
    res_bmc = requests.request("POST", BMC_URL, json=bmc_payload, headers=headers_bmc)

    print(f"🚀 Respuesta de BMC HelixGPT: {res_bmc.status_code}")

    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    # Arranca el servidor Flask en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)