import os
import json
import re
import time
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GROQ_API_KEY and not GEMINI_API_KEY:
    raise RuntimeError("Necesitas GROQ_API_KEY o GEMINI_API_KEY en las variables de entorno")

PROMPT_ANALIZAR = """Eres un asistente escolar. Analiza esta foto de un cuaderno o pizarra de clase.

Extrae la informacion y devuelve un JSON con este formato exacto:
{
  "materia": "nombre de la materia (si no se identifica, pon 'General')",
  "titulo": "tema principal de la clase",
  "contenido": "todo el contenido de la clase transcrito y organizado con formato markdown (usa ## para subtitulos, - para listas, **negrita** para conceptos clave, etc.)",
  "resumen": "resumen de 2-3 oraciones de lo que trata la clase"
}

IMPORTANTE:
- Transcribe TODO el texto visible, no resumas el contenido
- Organiza el contenido de forma clara con markdown
- Si hay diagramas o dibujos, describelos entre [corchetes]
- Si hay formulas matematicas, usalas con formato claro
- Responde SOLO con el JSON, sin texto adicional ni bloques de codigo
"""


def _llamar_groq(image_b64):
    """Llama a Groq API con Llama 4 Scout (vision)."""
    payload = json.dumps({
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_ANALIZAR},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        logger.error(f"Groq error {e.code}: {body}")
        raise RuntimeError(f"Groq API error {e.code}: {body}")

    return result["choices"][0]["message"]["content"]


def _llamar_gemini(image_b64):
    """Llama a Gemini API."""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[
            {
                "parts": [
                    {"text": PROMPT_ANALIZAR},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                ]
            }
        ],
    )
    return response.text


def analizar_imagen(image_b64, max_retries=3):
    """Analiza una imagen. Intenta Groq primero, si falla usa Gemini como fallback."""
    proveedores = []
    if GROQ_API_KEY:
        proveedores.append(("groq", _llamar_groq))
    if GEMINI_API_KEY:
        proveedores.append(("gemini", _llamar_gemini))

    last_error = None

    for nombre, llamar_fn in proveedores:
        for intento in range(max_retries):
            try:
                logger.info(f"Intentando con {nombre} (intento {intento + 1})")
                texto = llamar_fn(image_b64)

                texto = texto.strip()
                texto = re.sub(r"^```json\s*", "", texto)
                texto = re.sub(r"\s*```$", "", texto)

                return json.loads(texto)

            except Exception as e:
                last_error = e
                error_str = str(e)
                if ("429" in error_str or "rate" in error_str.lower()) and intento < max_retries - 1:
                    wait = (intento + 1) * 30
                    logger.warning(f"{nombre}: rate limit, reintentando en {wait}s")
                    time.sleep(wait)
                else:
                    logger.warning(f"{nombre} fallo: {error_str}")
                    break  # Salir del retry loop, probar siguiente proveedor

    raise last_error
