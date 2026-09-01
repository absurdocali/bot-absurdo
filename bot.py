import os
import hmac
import hashlib
import logging
from flask import Flask, request, abort
import requests
import unicodedata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("absurdo_bot")

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Absurdo Live", 200

@app.route('/privacy')
def privacy():
    return """
    <h1>Politica de Privacidad - ABSURDO VENTAS</h1>
    <p>Esta app usa la API de WhatsApp Business para atender a clientes de Absurdo.</p>
    <p>No vendemos datos. Solo usamos los mensajes para responder consultas.</p>
    <p>Contacto: felmontoya1234@gmail.com</p>
    <p>Para borrar tus datos escribenos a ese correo.</p>
    """, 200, {'Content-Type': 'text/html'}

# Evita que un atacante mande payloads gigantes al webhook (DoS básico)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64 KB es más que suficiente para un mensaje de WhatsApp

# NUNCA escribimos secretos aquí, los lee del servidor
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN","").strip()
PHONE_ID = os.environ.get("PHONE_ID","").strip()
TOKEN = os.environ.get("WHATSAPP_TOKEN","").strip()
APP_SECRET = os.environ.get("APP_SECRET","").strip()

# Fail-fast: si falta una variable crítica, el bot no debe arrancar
# "silenciosamente roto". Mejor un error claro al desplegar.
_REQUIRED_VARS = {
    "PHONE_ID": PHONE_ID,
    "WHATSAPP_TOKEN": TOKEN,
    "VERIFY_TOKEN": VERIFY_TOKEN,
    "APP_SECRET": APP_SECRET,
}
_missing = [name for name, val in _REQUIRED_VARS.items() if not val]
if _missing:
    raise RuntimeError(
        f"Faltan variables de entorno requeridas: {', '.join(_missing)}. "
        "El bot no debe arrancar sin ellas."
    )


def es_de_meta(payload: bytes, firma_recibida: str) -> bool:
    """Verifica que el payload realmente venga de Meta.

    IMPORTANTE: si no hay APP_SECRET configurado, se RECHAZA la petición
    (fail-closed). Antes se aceptaba todo (fail-open), lo cual permitía
    a cualquiera enviar mensajes falsos si el secreto no estaba seteado.
    """
    if not firma_recibida:
        return False
    firma_esperada = hmac.new(APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={firma_esperada}", firma_recibida)


def enviar_mensaje(para: str, texto: str) -> None:
    # Limita el texto a 1000 caracteres para evitar payloads excesivos
    texto = texto[:1000]
    url = f"https://graph.facebook.com/v22.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = {"messaging_product": "whatsapp", "to": para, "type": "text", "text": {"body": texto}}
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code >= 400:
            logger.warning("Fallo al enviar mensaje a %s: %s %s", para, resp.status_code, resp.text[:200])
    except requests.RequestException:
        logger.exception("Error de red enviando mensaje a %s", para)


def limpiar(texto: str) -> str:
    # Convierte "CatÁlogo" -> "catalogo" (minúscula y sin tildes)
    texto = texto.lower().strip()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto


@app.route('/webhook', methods=['GET'])
def verificar_webhook():
    token_recibido = request.args.get('hub.verify_token', '')
    # Comparación en tiempo constante en vez de == para evitar timing attacks
    if hmac.compare_digest(token_recibido, VERIFY_TOKEN):
        return request.args.get('hub.challenge', '')
    abort(403)


@app.route('/webhook', methods=['POST'])
def recibir_mensaje():
    firma = request.headers.get('X-Hub-Signature-256', '')
    #if not es_de_meta(request.data, firma):
     #   logger.warning("Firma inválida en /webhook, petición rechazada")
      #  abort(403)

    data = request.get_json(silent=True)
    if not data:
        return "OK", 200

    try:
        value = data['entry'][0]['changes'][0]['value']
        mensajes = value.get('messages')
        if not mensajes:
            # Puede ser un evento de estado (entregado/leído), no un mensaje
            return "OK", 200

        mensaje = mensajes[0]
        numero = mensaje['from']
        texto = mensaje.get('text', {}).get('body', '').lower()[:100]  # Solo 100 chars

        texto_limpio = limpiar(texto)

        saludos = ["hola", "ola", "holas", "hello", "hi", "buenas", "que hubo",
                   "quiubo", "q hubo", "hey", "holi", "buenos dias",
                   "buenas tardes", "buenas noches", "precio", "precios"]

        if any(s in texto_limpio for s in saludos):
            resp = """¡Ey, parce! 🖤 Bienvenido a Absurdo, soy Absu, tu parcero digital. ¿Qué más? Aquí puedes preguntarme por calidad, tallas, diseños, envíos o el estado de tu pedido. Tenemos camisetas bien chimbas y estampadas a mano. ¿Qué te gustaría saber?🔥

1️ Calidad
2 Tallas 
3 Catálogo
4 Envíos
5 Hablar con Daniel"""

        elif texto_limpio == "1" or any(m in texto_limpio for m in ["material", "calidad", "tela", "gruesa", "delgada"]):
            resp = "Todo es 100% algodón premium parce, no se encoge, no pica y no se pone motosa. Es gruesita pero fresca, una bacaneria 🖤"

        elif texto_limpio == "2" or any(t in texto_limpio for t in ["talla", "tallas"]):
            resp = "¡Claro parce! tanto para hombres como mujeres manejamos de la XS a la XL, en regular y oversize 🖤 ¿Cuál usas vos?🔥"

        elif texto_limpio == "3" or any(c in texto_limpio for c in ["catalogo", "catalago"]):
            resp = "¡Claro! Píllate todo lo que tenemos aquí parce 👉 https://wa.me/c/573166572773 🖤"

        elif texto_limpio == "4" or any(e in texto_limpio for e in ["envio", "envios", "llega", "ciudad", "demora", "tarda", "entrega"]):
            resp = "Hacemos envíos a toda Colombia parce 🖤 A Cali llega en 1-2 días y nacional 3-5 días. ¿Para qué ciudad es?"

        elif texto_limpio == "5" or any(p in texto_limpio for p in ["persona", "humano", "asesor"]):
            resp = "Listo parce, yo soy ABSU 🤖 ya le aviso a Daniel para que te escriba él mismo, dame 1 min 🖤"

        else:
            resp = "No te entendí bro 😅 escribe *hola* para ver el menú"

        enviar_mensaje(numero, resp)

    except Exception:
        # No mostramos el error al usuario externo, pero sí lo registramos
        # internamente para poder detectar payloads maliciosos o bugs.
        logger.exception("Error procesando mensaje entrante")

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
