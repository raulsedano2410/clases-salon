import os
import base64
import hmac
import hashlib
import logging
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

from database import init_db, guardar_clase, obtener_clases, obtener_clases_por_materia, obtener_materias
from ai_processor import analizar_imagen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default_secret")

init_db()


# ─── Pagina web ───

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/clases")
def api_clases():
    materia = request.args.get("materia")
    if materia:
        clases = obtener_clases_por_materia(materia)
    else:
        clases = obtener_clases()
    return jsonify(clases)


@app.route("/api/materias")
def api_materias():
    return jsonify(obtener_materias())


# ─── Telegram Webhook ───

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False}), 400

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")

    # Solo procesar fotos
    photo = message.get("photo")
    if not photo:
        _enviar_mensaje(chat_id, "Enviame una foto del cuaderno o la pizarra y la proceso para la pagina de clases.")
        return jsonify({"ok": True})

    # Tomar la foto de mayor resolucion
    file_id = photo[-1]["file_id"]

    try:
        _enviar_mensaje(chat_id, "Recibida. Analizando con IA...")

        # Descargar la foto via Telegram API
        image_bytes = _descargar_foto(file_id)
        image_b64 = base64.b64encode(image_bytes).decode()

        # Analizar con Gemini
        resultado = analizar_imagen(image_b64)

        # Guardar en la base de datos
        guardar_clase(
            materia=resultado["materia"],
            titulo=resultado["titulo"],
            contenido=resultado["contenido"],
            resumen=resultado.get("resumen", ""),
        )

        _enviar_mensaje(
            chat_id,
            f"Clase guardada!\n\n"
            f"Materia: {resultado['materia']}\n"
            f"Tema: {resultado['titulo']}\n"
            f"Resumen: {resultado.get('resumen', 'N/A')}\n\n"
            f"Ya esta disponible en la pagina web."
        )

    except Exception as e:
        logger.error(f"Error procesando imagen: {e}", exc_info=True)
        _enviar_mensaje(chat_id, f"Error al procesar la imagen. Intenta de nuevo con una foto mas clara.")

    return jsonify({"ok": True})


def _descargar_foto(file_id):
    """Descarga una foto de Telegram por su file_id."""
    import urllib.request
    import json

    # Obtener file_path
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    with urllib.request.urlopen(url) as resp:
        file_info = json.loads(resp.read())
    file_path = file_info["result"]["file_path"]

    # Descargar archivo
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    with urllib.request.urlopen(download_url) as resp:
        return resp.read()


def _enviar_mensaje(chat_id, texto):
    """Envia un mensaje de texto via Telegram."""
    import urllib.request
    import urllib.parse
    import json

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": texto}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)


# ─── Setup del webhook (llamar una vez) ───

@app.route("/setup-webhook")
def setup_webhook():
    """Visitar esta URL una vez para registrar el webhook en Telegram."""
    import urllib.request
    import json

    app_url = os.environ.get("APP_URL", "").rstrip("/")
    if not app_url:
        return "Falta APP_URL en las variables de entorno", 400

    webhook_url = f"{app_url}/webhook/{WEBHOOK_SECRET}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"

    with urllib.request.urlopen(url) as resp:
        result = json.loads(resp.read())

    if result.get("ok"):
        return f"Webhook configurado: {webhook_url}"
    return f"Error: {result}", 400


if __name__ == "__main__":
    app.run(debug=True, port=5000)
