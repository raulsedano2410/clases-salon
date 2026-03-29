import os
import json
import re
import time
import logging
from google import genai

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"

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


def analizar_imagen(image_bytes, max_retries=3):
    """Analiza una imagen de cuaderno/pizarra y extrae el contenido estructurado."""
    for intento in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[
                    {
                        "parts": [
                            {"text": PROMPT_ANALIZAR},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_bytes}},
                        ]
                    }
                ],
            )

            texto = response.text.strip()
            # Limpiar bloques de codigo markdown si los hay
            texto = re.sub(r"^```json\s*", "", texto)
            texto = re.sub(r"\s*```$", "", texto)

            return json.loads(texto)

        except Exception as e:
            if "429" in str(e) and intento < max_retries - 1:
                wait = (intento + 1) * 30
                logger.warning(f"Rate limit alcanzado, reintentando en {wait}s (intento {intento + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
