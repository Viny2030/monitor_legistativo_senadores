import os
from fastapi import APIRouter
import psycopg2
import psycopg2.extras

_raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL") or ""
DATABASE_URL = _raw.replace("postgres://", "postgresql://", 1)

router = APIRouter(prefix="/db", tags=["base de datos"])

def get_conn():
    return psycopg2.connect(DATABASE_URL)

@router.get("/senadores")
def get_senadores(fecha: str = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM senadores WHERE fecha_datos = %s ORDER BY nombre", (fecha,))
    else:
        cur.execute("SELECT * FROM senadores WHERE fecha_datos = (SELECT MAX(fecha_datos) FROM senadores) ORDER BY nombre")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"senadores": [dict(r) for r in rows], "total": len(rows)}

@router.get("/reporte-partido")
def get_reporte_partido(fecha: str = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos = %s ORDER BY bancas DESC", (fecha,))
    else:
        cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos = (SELECT MAX(fecha_datos) FROM reporte_partido) ORDER BY bancas DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"reporte_partido": [dict(r) for r in rows]}

@router.get("/reporte-provincial")
def get_reporte_provincial(fecha: str = None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos = %s ORDER BY participation_pct DESC", (fecha,))
    else:
        cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos = (SELECT MAX(fecha_datos) FROM reporte_provincial) ORDER BY participation_pct DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"reporte_provincial": [dict(r) for r in rows]}

@router.get("/fechas")
def get_fechas_disponibles():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT fecha_datos FROM senadores ORDER BY fecha_datos DESC")
    fechas = [str(r[0]) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return {"fechas": fechas}