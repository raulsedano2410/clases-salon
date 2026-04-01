import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "Falta DATABASE_URL. Crea un proyecto gratis en https://supabase.com "
        "y copia la connection string de Settings > Database > Connection string > URI"
    )


def get_db():
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clases (
            id SERIAL PRIMARY KEY,
            materia TEXT NOT NULL,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            resumen TEXT,
            fecha TEXT NOT NULL,
            imagen_url TEXT,
            creado_en TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Base de datos inicializada (PostgreSQL)")


def guardar_clase(materia, titulo, contenido, resumen, fecha=None, imagen_url=None):
    conn = get_db()
    cur = conn.cursor()
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")
    cur.execute(
        "INSERT INTO clases (materia, titulo, contenido, resumen, fecha, imagen_url) VALUES (%s, %s, %s, %s, %s, %s)",
        (materia, titulo, contenido, resumen, fecha, imagen_url),
    )
    conn.commit()
    cur.close()
    conn.close()


def obtener_clases(limit=50):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, materia, titulo, contenido, resumen, fecha, imagen_url, creado_en FROM clases ORDER BY fecha DESC, id DESC LIMIT %s",
        (limit,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    # Convertir datetime a string para JSON
    for r in rows:
        if r.get("creado_en"):
            r["creado_en"] = str(r["creado_en"])
    return rows


def obtener_clases_por_materia(materia):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, materia, titulo, contenido, resumen, fecha, imagen_url, creado_en FROM clases WHERE materia = %s ORDER BY fecha DESC, id DESC",
        (materia,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        if r.get("creado_en"):
            r["creado_en"] = str(r["creado_en"])
    return rows


def obtener_materias():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT materia FROM clases ORDER BY materia")
    materias = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return materias
