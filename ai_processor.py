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

PROMPT_ANALIZAR = """Eres un asistente escolar experto. Analiza esta foto de un cuaderno o pizarra de clase.

Extrae la informacion y devuelve un JSON con este formato exacto:
{
  "titulo": "tema principal de la clase",
  "contenido": "todo el contenido transcrito y organizado con formato markdown",
  "resumen": "resumen de 2-3 oraciones",
  "diagramas": ["codigo mermaid del diagrama 1", "codigo mermaid del diagrama 2"]
}

REGLAS PARA EL CONTENIDO:
- Transcribe TODO el texto visible, no resumas
- Usa markdown: ## subtitulos, - listas, **negrita** para conceptos clave
- Si hay formulas matematicas, escribelas con formato claro

REGLAS PARA DIAGRAMAS (campo "diagramas"):
Si la imagen contiene diagramas visuales (lineas de tiempo, mapas conceptuales, diagramas de flujo, cuadros sinopticos, organigramas, tablas comparativas), genera codigo Mermaid que los reproduzca.

Tipos de Mermaid segun el diagrama:
- Linea de tiempo → usa "timeline"
- Mapa conceptual / mapa mental → usa "mindmap"
- Diagrama de flujo / proceso → usa "flowchart LR" o "flowchart TD"
- Cuadro sinoptico → usa "mindmap"
- Organigrama / jerarquia → usa "flowchart TD"
- Ciclo / proceso circular → usa "flowchart LR" con conexiones circulares

Ejemplo de timeline:
timeline
    title Historia del Peru
    Periodo Autoctono : Cultura Chavin
                      : Imperio Wari
    Periodo Colonial : 1532 Francisco Pizarro
                     : 1542 Virreinato

Ejemplo de mindmap:
mindmap
  root((Tema Central))
    Subtema 1
      Detalle A
      Detalle B
    Subtema 2
      Detalle C

Ejemplo de flowchart:
flowchart TD
    A[Inicio] --> B[Paso 1]
    B --> C{Decision}
    C -->|Si| D[Resultado A]
    C -->|No| E[Resultado B]

IMPORTANTE:
- Si NO hay diagramas en la imagen, pon "diagramas": []
- Cada diagrama es un string separado en el array
- El codigo Mermaid NO debe tener comillas invertidas (```)
- Incluye TODA la informacion del diagrama original, no simplifiques
- Responde SOLO con el JSON, sin texto adicional ni bloques de codigo
"""

PROMPT_FUSIONAR = """Tienes apuntes existentes y contenido nuevo de la MISMA clase.
Fusionalos en un solo documento coherente.

REGLAS:
- Ordena el contenido logicamente (introduccion → desarrollo → cierre) sin importar el orden en que llego
- Elimina contenido duplicado
- Mantiene formato markdown (## subtitulos, - listas, **negrita** para conceptos clave)
- NO pierdas informacion, incluye TODO

APUNTES EXISTENTES:
{existente}

CONTENIDO NUEVO:
{nuevo}

Devuelve SOLO un JSON con este formato:
{{"titulo": "tema actualizado de la clase", "contenido": "contenido fusionado completo en markdown", "resumen": "resumen actualizado de 2-3 oraciones"}}
"""


def _llamar_openai_compatible(api_url, api_key, model, messages):
    """Llamada generica a cualquier API compatible con OpenAI."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
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


def _llamar_groq(messages):
    return _llamar_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        GROQ_API_KEY,
        "meta-llama/llama-4-scout-17b-16e-instruct",
        messages,
    )


def _llamar_huggingface(messages):
    return _llamar_openai_compatible(
        "https://router.huggingface.co/v1/chat/completions",
        HF_TOKEN,
        "meta-llama/Llama-4-Scout-17B-16E-Instruct:fastest",
        messages,
    )


def _llamar_gemini_vision(image_b64, prompt_text):
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[
            {
                "parts": [
                    {"text": prompt_text},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                ]
            }
        ],
    )
    return response.text


def _llamar_gemini_texto(prompt_text):
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=[{"parts": [{"text": prompt_text}]}],
    )
    return response.text


def _parsear_json(texto):
    """Limpia y parsea JSON de la respuesta de la IA."""
    texto = texto.strip()
    texto = re.sub(r"^```json\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)
    return json.loads(texto)


def _intentar_proveedores(fn_por_proveedor, max_retries=2):
    """Intenta multiples proveedores con retry."""
    last_error = None
    for nombre, llamar_fn in fn_por_proveedor:
        for intento in range(max_retries):
            try:
                logger.info(f"Intentando con {nombre} (intento {intento + 1})")
                texto = llamar_fn()
                return _parsear_json(texto)
            except Exception as e:
                last_error = e
                error_str = str(e)
                logger.warning(f"{nombre} fallo: {error_str[:200]}")
                if ("429" in error_str or "rate" in error_str.lower()) and intento < max_retries - 1:
                    time.sleep((intento + 1) * 30)
                else:
                    break
    raise last_error


def analizar_imagen(image_b64):
    """Analiza una imagen de cuaderno/pizarra. Devuelve {titulo, contenido, resumen}."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT_ANALIZAR},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }
    ]

    proveedores = []
    if HF_TOKEN:
        proveedores.append(("huggingface", lambda: _llamar_huggingface(messages)))
    if GROQ_API_KEY:
        proveedores.append(("groq", lambda: _llamar_groq(messages)))
    if GEMINI_API_KEY:
        proveedores.append(("gemini", lambda: _llamar_gemini_vision(image_b64, PROMPT_ANALIZAR)))

    return _intentar_proveedores(proveedores)


def fusionar_contenidos(contenido_existente, contenido_nuevo):
    """Fusiona contenido existente con contenido nuevo usando IA."""
    prompt = PROMPT_FUSIONAR.format(existente=contenido_existente, nuevo=contenido_nuevo)
    messages = [{"role": "user", "content": prompt}]

    proveedores = []
    if HF_TOKEN:
        proveedores.append(("huggingface", lambda: _llamar_huggingface(messages)))
    if GROQ_API_KEY:
        proveedores.append(("groq", lambda: _llamar_groq(messages)))
    if GEMINI_API_KEY:
        proveedores.append(("gemini", lambda: _llamar_gemini_texto(prompt)))

    return _intentar_proveedores(proveedores)
