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
            creado_en TIMESTAMP NOT NULL DEFAULT NOW(),
            actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_photos (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            file_id TEXT NOT NULL,
            image_b64 TEXT NOT NULL,
            creado_en TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Base de datos inicializada (PostgreSQL)")


# ─── Fotos pendientes ───

def guardar_foto_pendiente(chat_id, file_id, image_b64):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO pending_photos (chat_id, file_id, image_b64) VALUES (%s, %s, %s)",
        (chat_id, file_id, image_b64),
    )
    conn.commit()
    cur.close()
    conn.close()


def contar_fotos_pendientes(chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pending_photos WHERE chat_id = %s", (chat_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count


def obtener_fotos_pendientes(chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, image_b64 FROM pending_photos WHERE chat_id = %s ORDER BY creado_en ASC",
        (chat_id,),
    )
    rows = [{"id": r[0], "image_b64": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def eliminar_fotos_pendientes(chat_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_photos WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()


# ─── Clases ───

def obtener_clase_por_materia_fecha(materia, fecha):
    """Busca una clase existente para materia+fecha (para merge)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, titulo, contenido, resumen FROM clases WHERE materia = %s AND fecha = %s",
        (materia, fecha),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"id": row[0], "titulo": row[1], "contenido": row[2], "resumen": row[3]}
    return None


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


def actualizar_clase(clase_id, titulo, contenido, resumen):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE clases SET titulo = %s, contenido = %s, resumen = %s, actualizado_en = NOW() WHERE id = %s",
        (titulo, contenido, resumen, clase_id),
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
    for r in rows:
        if r.get("creado_en"):
            r["creado_en"] = str(r["creado_en"])
    return rows


def obtener_clases_por_fecha(fecha):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, materia, titulo, contenido, resumen, fecha, imagen_url, creado_en FROM clases WHERE fecha = %s ORDER BY materia",
        (fecha,),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    for r in rows:
        if r.get("creado_en"):
            r["creado_en"] = str(r["creado_en"])
    return rows


def obtener_clases_por_materia_fecha(materia, fecha):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, materia, titulo, contenido, resumen, fecha, imagen_url, creado_en FROM clases WHERE materia = %s AND fecha = %s ORDER BY id DESC",
        (materia, fecha),
    )
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
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
