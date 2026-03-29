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
HF_TOKEN = os.environ.get("HF_TOKEN")

if not GROQ_API_KEY and not GEMINI_API_KEY and not HF_TOKEN:
    raise RuntimeError("Necesitas GROQ_API_KEY, GEMINI_API_KEY o HF_TOKEN en las variables de entorno")

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


def _llamar_openai_compatible(api_url, api_key, model, image_b64):
    """Llamada generica a cualquier API compatible con OpenAI (Groq, HuggingFace, etc.)."""
    payload = json.dumps({
        "model": model,
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
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        logger.error(f"API error {e.code}: {body[:500]}")
        raise RuntimeError(f"API error {e.code}: {body[:200]}")

    return result["choices"][0]["message"]["content"]


def _llamar_groq(image_b64):
    return _llamar_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        GROQ_API_KEY,
        "meta-llama/llama-4-scout-17b-16e-instruct",
        image_b64,
    )


def _llamar_huggingface(image_b64):
    return _llamar_openai_compatible(
        "https://router.huggingface.co/v1/chat/completions",
        HF_TOKEN,
        "meta-llama/Llama-4-Scout-17B-16E-Instruct:fastest",
        image_b64,
    )


def _llamar_gemini(image_b64):
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


def analizar_imagen(image_b64, max_retries=2):
    """Analiza una imagen. Intenta proveedores en orden hasta que uno funcione."""
    proveedores = []
    if HF_TOKEN:
        proveedores.append(("huggingface", _llamar_huggingface))
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
                logger.warning(f"{nombre} fallo: {error_str[:200]}")
                if ("429" in error_str or "rate" in error_str.lower()) and intento < max_retries - 1:
                    wait = (intento + 1) * 30
                    logger.warning(f"{nombre}: rate limit, esperando {wait}s")
                    time.sleep(wait)
                else:
                    break  # Probar siguiente proveedor

    raise last_error
