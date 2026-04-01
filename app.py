import os
import base64
import logging
import json
import urllib.request
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, guardar_clase, actualizar_clase, obtener_clases, obtener_clases_por_fecha,
    obtener_clases_por_materia, obtener_clases_por_materia_fecha, obtener_materias,
    obtener_clase_por_materia_fecha, guardar_foto_pendiente, obtener_fotos_pendientes,
    eliminar_fotos_pendientes, contar_fotos_pendientes,
)
from ai_processor import analizar_imagen, fusionar_contenidos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "default_secret")

MATERIAS = ["Lenguaje", "Matematicas", "CTA", "Ingles", "Historia", "Quimica", "E. Fisica"]

init_db()


# ─── Pagina web ───

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/clases")
def api_clases():
    materia = request.args.get("materia")
    fecha = request.args.get("fecha")
    if fecha and materia:
        clases = obtener_clases_por_materia_fecha(materia, fecha)
    elif fecha:
        clases = obtener_clases_por_fecha(fecha)
    elif materia:
        clases = obtener_clases_por_materia(materia)
    else:
        clases = obtener_clases()
    return jsonify(clases)


@app.route("/api/materias")
def api_materias():
    return jsonify(MATERIAS)


# ─── Telegram Webhook ───

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False}), 400

    # Manejar callback_query (boton de materia presionado)
    callback = data.get("callback_query")
    if callback:
        return _manejar_callback(callback)

    # Manejar mensaje normal (foto o texto)
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return jsonify({"ok": True})

    photo = message.get("photo")
    if not photo:
        _enviar_mensaje(chat_id, "Enviame una foto del cuaderno o pizarra y selecciona la materia.")
        return jsonify({"ok": True})

    # Guardar foto pendiente
    file_id = photo[-1]["file_id"]
    try:
        image_bytes = _descargar_foto(file_id)
        image_b64 = base64.b64encode(image_bytes).decode()
        guardar_foto_pendiente(chat_id, file_id, image_b64)
        num_fotos = contar_fotos_pendientes(chat_id)

        if num_fotos == 1:
            texto = "Foto recibida. Selecciona la materia:"
        else:
            texto = f"{num_fotos} fotos listas. Selecciona la materia:"

        _enviar_teclado_materias(chat_id, texto)

    except Exception as e:
        logger.error(f"Error guardando foto: {e}", exc_info=True)
        _enviar_mensaje(chat_id, "Error al recibir la foto. Intenta de nuevo.")

    return jsonify({"ok": True})


def _manejar_callback(callback):
    """Procesa la seleccion de materia desde el teclado inline."""
    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    callback_data = callback.get("data", "")

    # Responder callback inmediatamente (quita el relojito)
    _answer_callback(callback_id)

    if not callback_data.startswith("materia:"):
        return jsonify({"ok": True})

    materia = callback_data.split(":", 1)[1]

    # Obtener fotos pendientes
    fotos = obtener_fotos_pendientes(chat_id)
    if not fotos:
        _enviar_mensaje(chat_id, "No hay fotos pendientes. Envia una foto primero.")
        return jsonify({"ok": True})

    _enviar_mensaje(chat_id, f"Procesando {len(fotos)} foto(s) de {materia} con IA...")

    try:
        # Analizar cada foto
        resultados = []
        for foto in fotos:
            resultado = analizar_imagen(foto["image_b64"])
            resultados.append(resultado)

        # Fusionar resultados de multiples fotos
        if len(resultados) == 1:
            titulo = resultados[0]["titulo"]
            contenido = resultados[0]["contenido"]
            resumen = resultados[0].get("resumen", "")
        else:
            # Fusionar progresivamente
            contenido_acumulado = resultados[0]["contenido"]
            for r in resultados[1:]:
                merged = fusionar_contenidos(contenido_acumulado, r["contenido"])
                contenido_acumulado = merged["contenido"]
            titulo = merged.get("titulo", resultados[0]["titulo"])
            contenido = contenido_acumulado
            resumen = merged.get("resumen", resultados[0].get("resumen", ""))

        # Verificar si ya existe clase para esta materia+hoy → merge
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        clase_existente = obtener_clase_por_materia_fecha(materia, fecha_hoy)

        if clase_existente:
            merged = fusionar_contenidos(clase_existente["contenido"], contenido)
            actualizar_clase(
                clase_existente["id"],
                merged.get("titulo", titulo),
                merged["contenido"],
                merged.get("resumen", resumen),
            )
            accion = "actualizada"
        else:
            guardar_clase(materia=materia, titulo=titulo, contenido=contenido, resumen=resumen)
            accion = "guardada"

        # Limpiar fotos pendientes
        eliminar_fotos_pendientes(chat_id)

        _enviar_mensaje(
            chat_id,
            f"Clase {accion}!\n\n"
            f"Materia: {materia}\n"
            f"Tema: {titulo}\n"
            f"Resumen: {resumen}\n\n"
            f"Ya esta en la pagina web."
        )

    except Exception as e:
        logger.error(f"Error procesando imagenes: {e}", exc_info=True)
        _enviar_mensaje(chat_id, "Error al procesar las fotos. Intenta de nuevo.")

    return jsonify({"ok": True})


# ─── Helpers de Telegram ───

def _descargar_foto(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    with urllib.request.urlopen(url) as resp:
        file_info = json.loads(resp.read())
    file_path = file_info["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    with urllib.request.urlopen(download_url) as resp:
        return resp.read()


def _enviar_mensaje(chat_id, texto):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": texto}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)


def _enviar_teclado_materias(chat_id, texto):
    """Envia mensaje con teclado inline de materias."""
    keyboard = []
    row = []
    for i, materia in enumerate(MATERIAS):
        row.append({"text": materia, "callback_data": f"materia:{materia}"})
        if len(row) == 2 or i == len(MATERIAS) - 1:
            keyboard.append(row)
            row = []

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": texto,
        "reply_markup": {"inline_keyboard": keyboard},
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)


def _answer_callback(callback_query_id):
    """Responde al callback query para quitar el indicador de carga."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = json.dumps({"callback_query_id": callback_query_id}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass


# ─── Setup del webhook ───

@app.route("/setup-webhook")
def setup_webhook():
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
