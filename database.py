import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "clases.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            materia TEXT NOT NULL,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            resumen TEXT,
            fecha TEXT NOT NULL,
            imagen_url TEXT,
            creado_en TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def guardar_clase(materia, titulo, contenido, resumen, fecha=None, imagen_url=None):
    conn = get_db()
    if not fecha:
        fecha = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO clases (materia, titulo, contenido, resumen, fecha, imagen_url) VALUES (?, ?, ?, ?, ?, ?)",
        (materia, titulo, contenido, resumen, fecha, imagen_url),
    )
    conn.commit()
    conn.close()


def obtener_clases(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM clases ORDER BY fecha DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_clases_por_materia(materia):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM clases WHERE materia = ? ORDER BY fecha DESC, id DESC",
        (materia,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_materias():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT materia FROM clases ORDER BY materia"
    ).fetchall()
    conn.close()
    return [r["materia"] for r in rows]
