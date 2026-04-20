"""
api/run_senado.py — API standalone del módulo Senado
Uso: python api/run_senado.py
Docs: http://localhost:8000/docs
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import psycopg2
import psycopg2.extras
import pandas as pd
from glob import glob

app = FastAPI(
    title="Monitor Legislativo — Senado Nacional",
    description="72 senadores · participación, votos y reportes por partido/provincia",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Servir dashboard como archivos estáticos
_DASHBOARD = Path(__file__).parent.parent / "dashboard"
if _DASHBOARD.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD), html=True), name="dashboard")

DATA_DIR = Path(__file__).parent.parent / "data"

def _latest_csv(pattern: str) -> Path | None:
    files = sorted(glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(files[0]) if files else None

_DB_URL = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")

def _db():
    return psycopg2.connect(_DB_URL)


# ── Endpoints base de datos ──────────────────────────────────────────

@app.get("/db/senadores")
def db_senadores(fecha: str = None):
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM senadores WHERE fecha_datos=%s ORDER BY nombre", (fecha,))
    else:
        cur.execute("SELECT * FROM senadores WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM senadores) ORDER BY nombre")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"senadores": rows, "total": len(rows)}

@app.get("/db/reporte-partido")
def db_reporte_partido(fecha: str = None):
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos=%s ORDER BY bancas DESC", (fecha,))
    else:
        cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM reporte_partido) ORDER BY bancas DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"reporte_partido": rows}

@app.get("/db/reporte-provincial")
def db_reporte_provincial(fecha: str = None):
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if fecha:
        cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos=%s ORDER BY participation_pct DESC", (fecha,))
    else:
        cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM reporte_provincial) ORDER BY participation_pct DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"reporte_provincial": rows}

@app.get("/db/fechas")
def db_fechas():
    conn = _db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT fecha_datos FROM senadores ORDER BY fecha_datos DESC")
    fechas = [str(r[0]) for r in cur.fetchall()]
    conn.close()
    return {"fechas": fechas}


# ── Endpoints raíz y salud ───────────────────────────────────────────

@app.get("/")
def raiz():
    return {
        "proyecto": "Monitor Legislativo — Senado Nacional Argentina",
        "version": "1.0.0",
        "endpoints": {
            "senadores":          "/senado/senadores",
            "reporte_partido":    "/senado/reporte-partido",
            "reporte_provincial": "/senado/reporte-provincial",
            "db_senadores":       "/db/senadores",
            "db_fechas":          "/db/fechas",
            "salud":              "/salud",
            "docs":               "/docs",
            "dashboard":          "/dashboard/senado.html",
            "indicadores":        "/dashboard/indicadores.html",
        },
    }


@app.get("/salud")
def salud():
    csv = _latest_csv("senadores_*.csv")
    return {"status": "ok", "csv": csv.name if csv else None}


@app.get("/senado/senadores")
def get_senadores():
    csv = _latest_csv("senadores_*.csv")
    if not csv:
        return JSONResponse({"ok": False, "senadores": [], "fuente": "csv_no_encontrado"})
    df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
    registros = []
    for _, row in df.iterrows():
        def safe_int(v):
            try: return int(float(v)) if pd.notna(v) else 0
            except: return 0
        def safe_float(v):
            try: return float(v) if pd.notna(v) else None
            except: return None
        registros.append({
            "id":                str(row.get("id", "")),
            "nombre":            str(row.get("nombre", "—")),
            "provincia":         str(row.get("provincia", "—")),
            "partido":           str(row.get("partido_normalizado", row.get("partido", "—"))),
            "rol_provincial":    str(row.get("rol_provincial", "—")),
            "votos_total":       safe_int(row.get("votos_total")),
            "votos_afirmativos": safe_int(row.get("votos_afirmativos")),
            "votos_negativos":   safe_int(row.get("votos_negativos")),
            "abstenciones":      safe_int(row.get("abstenciones")),
            "ausencias":         safe_int(row.get("ausencias")),
            "participation_pct": safe_float(row.get("participation_pct")),
            "foto":              str(row.get("foto", "")),
            "email":             str(row.get("email", "")),
            "fuente":            "csv_real",
        })
    return JSONResponse({"ok": True, "total": len(registros), "senadores": registros, "fuente": csv.name})


@app.get("/senado/reporte-partido")
def get_reporte_partido():
    csv = _latest_csv("reporte_partido_senado_*.csv")
    if not csv:
        return JSONResponse({"ok": False, "partidos": [], "fuente": "csv_no_encontrado"})
    df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
    return JSONResponse({"ok": True, "total": len(df), "partidos": df.to_dict("records"), "fuente": csv.name})


@app.get("/senado/reporte-provincial")
def get_reporte_provincial():
    csv = _latest_csv("reporte_provincial_senado_*.csv")
    if not csv:
        return JSONResponse({"ok": False, "provincias": [], "fuente": "csv_no_encontrado"})
    df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
    return JSONResponse({"ok": True, "total": len(df), "provincias": df.to_dict("records"), "fuente": csv.name})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.run_senado:app", host="0.0.0.0", port=8000, reload=True)
