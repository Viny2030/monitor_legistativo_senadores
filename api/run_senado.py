"""
api/run_senado.py — API standalone del módulo Senado
Uso: uvicorn api.run_senado:app --host 0.0.0.0 --port $PORT
Docs: /docs
"""
from __future__ import annotations
import sys
import os
import datetime
import decimal
from pathlib import Path
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from glob import glob

# ── Corrección Railway: "postgres://" → "postgresql://" ──────────────────────
_raw_db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL") or ""
_DB_URL = _raw_db_url.replace("postgres://", "postgresql://", 1)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # crea data/ si no existe


def _serialize(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    return str(obj)


def _rows_to_json(rows):
    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if v is None:
                clean[k] = None
            elif isinstance(v, (datetime.date, datetime.datetime)):
                clean[k] = v.isoformat()
            elif isinstance(v, decimal.Decimal):
                clean[k] = float(v)
            elif isinstance(v, (int, float, bool, str)):
                clean[k] = v
            else:
                clean[k] = str(v)
        result.append(clean)
    return result


def _db():
    if not _DB_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(_DB_URL)


def _latest_csv(pattern: str):
    files = sorted(glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(files[0]) if files else None


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Intentar inicializar DB — nunca crashear si falla
    if _DB_URL:
        try:
            from db.schema import crear_tablas
            crear_tablas()
            print("✅ Tablas DB inicializadas")
        except Exception as e:
            print(f"⚠️  DB al arrancar (no crítico): {e}")
    else:
        print("ℹ️  DATABASE_URL no configurada — /db/* no disponible, CSV/fallback activo")
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Monitor Legislativo — Senado Nacional",
    description="72 senadores · participación, votos y reportes por partido/provincia",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Servir dashboard como archivos estáticos
_DASHBOARD = Path(__file__).parent.parent / "dashboard"
if _DASHBOARD.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD), html=True), name="dashboard")
    print(f"✅ Dashboard montado desde {_DASHBOARD}")
else:
    print(f"⚠️  Carpeta dashboard/ no encontrada en {_DASHBOARD}")


# ── Endpoints DB ──────────────────────────────────────────────────────────────
@app.get("/db/senadores")
def db_senadores(fecha: str = None):
    try:
        import psycopg2.extras
        conn = _db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if fecha:
            cur.execute("SELECT * FROM senadores WHERE fecha_datos=%s ORDER BY nombre", (fecha,))
        else:
            cur.execute("SELECT * FROM senadores WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM senadores) ORDER BY nombre")
        rows = _rows_to_json([dict(r) for r in cur.fetchall()])
        conn.close()
        return JSONResponse({"ok": True, "senadores": rows, "total": len(rows)})
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


@app.get("/db/reporte-partido")
def db_reporte_partido(fecha: str = None):
    try:
        import psycopg2.extras
        conn = _db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if fecha:
            cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos=%s ORDER BY bancas DESC", (fecha,))
        else:
            cur.execute("SELECT * FROM reporte_partido WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM reporte_partido) ORDER BY bancas DESC")
        rows = _rows_to_json([dict(r) for r in cur.fetchall()])
        conn.close()
        return JSONResponse({"ok": True, "reporte_partido": rows, "total": len(rows)})
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


@app.get("/db/reporte-provincial")
def db_reporte_provincial(fecha: str = None):
    try:
        import psycopg2.extras
        conn = _db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if fecha:
            cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos=%s ORDER BY participation_pct DESC", (fecha,))
        else:
            cur.execute("SELECT * FROM reporte_provincial WHERE fecha_datos=(SELECT MAX(fecha_datos) FROM reporte_provincial) ORDER BY participation_pct DESC")
        rows = _rows_to_json([dict(r) for r in cur.fetchall()])
        conn.close()
        return JSONResponse({"ok": True, "reporte_provincial": rows, "total": len(rows)})
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


@app.get("/db/fechas")
def db_fechas():
    try:
        conn = _db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT fecha_datos FROM senadores ORDER BY fecha_datos DESC")
        fechas = [str(r[0]) for r in cur.fetchall()]
        conn.close()
        return {"fechas": fechas}
    except Exception as e:
        return JSONResponse(status_code=503, content={"ok": False, "error": str(e)})


# ── Endpoints CSV ─────────────────────────────────────────────────────────────
@app.get("/senado/senadores")
def get_senadores():
    try:
        import pandas as pd
        csv = _latest_csv("senadores_*.csv")
        if not csv:
            return JSONResponse({"ok": False, "senadores": [], "fuente": "csv_no_encontrado",
                                 "mensaje": "No hay CSV en data/. Ejecutar pipeline.py primero."})
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
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/senado/reporte-partido")
def get_reporte_partido():
    try:
        import pandas as pd
        csv = _latest_csv("reporte_partido_senado_*.csv")
        if not csv:
            return JSONResponse({"ok": False, "partidos": [], "fuente": "csv_no_encontrado"})
        df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
        return JSONResponse({"ok": True, "total": len(df), "partidos": df.to_dict("records"), "fuente": csv.name})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


@app.get("/senado/reporte-provincial")
def get_reporte_provincial():
    try:
        import pandas as pd
        csv = _latest_csv("reporte_provincial_senado_*.csv")
        if not csv:
            return JSONResponse({"ok": False, "provincias": [], "fuente": "csv_no_encontrado"})
        df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
        return JSONResponse({"ok": True, "total": len(df), "provincias": df.to_dict("records"), "fuente": csv.name})
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})


# ── Endpoints Agentic AI ──────────────────────────────────────────────────────
# agentic_ai.py está en la raíz del repo (mismo patrón que monitor_legistativo/
# Diputados): explicaciones en lenguaje natural (Claude, opcional) + detección
# autónoma de anomalías con reglas estadísticas (siempre disponible — es el
# mismo análisis que corre scripts/agente_monitor.py en el workflow diario,
# expuesto acá para verlo on-demand).
from pydantic import BaseModel
from agentic_ai import (  # noqa: E402
    explicar, ia_disponible, detectar_anomalias, resumen_diario, chat_con_tools,
)


class ExplicarIARequest(BaseModel):
    tipo: str = "senador"
    datos: dict = {}


def _cargar_datos_para_ia():
    """Nómina actual + anterior (los dos senadores_*.csv más recientes) y
    dieta.json — mismo criterio que scripts/agente_monitor.py, reimplementado
    acá sin importar scripts/ para no acoplar la API a un módulo pensado para
    correr standalone en CI."""
    import re
    import json
    import pandas as pd

    archivos = sorted(glob(str(DATA_DIR / "senadores_*.csv")), reverse=True)
    if not archivos:
        return None, None, None, None
    csv_actual = Path(archivos[0])
    csv_anterior = Path(archivos[1]) if len(archivos) > 1 else None

    def cargar(path):
        df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")

        def safe_int(v):
            try: return int(float(v)) if pd.notna(v) else 0
            except Exception: return 0

        def safe_float(v):
            try: return float(v) if pd.notna(v) else None
            except Exception: return None

        return [{
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
        } for _, row in df.iterrows()]

    senadores_actual = cargar(csv_actual)
    senadores_anterior = cargar(csv_anterior) if csv_anterior else None
    m = re.search(r"senadores_(\d{4}-\d{2}-\d{2})\.csv$", csv_actual.name)
    fecha_datos = m.group(1) if m else None

    dieta_path = Path(__file__).parent.parent / "dieta.json"
    dieta = None
    if dieta_path.exists():
        try:
            dieta = json.load(open(dieta_path, encoding="utf-8"))
        except Exception:
            dieta = None

    return senadores_actual, senadores_anterior, dieta, fecha_datos


@app.get("/ia/status")
def ia_status():
    return {"disponible": ia_disponible()}


@app.post("/ia/explicar")
def ia_explicar(req: ExplicarIARequest):
    return explicar(req.tipo, req.datos)


@app.get("/ia/anomalias")
def ia_anomalias():
    """
    Agente autónomo (parte 1): corre las reglas de detección de anomalías
    sobre los CSV actuales de data/. No depende de Claude/ANTHROPIC_API_KEY
    — siempre devuelve hallazgos estructurados (participación crítica,
    composición incompleta, outliers estadísticos, datos desactualizados,
    recibo oficial de dieta desactualizado).
    """
    senadores, senadores_ant, dieta, fecha_datos = _cargar_datos_para_ia()
    if senadores is None:
        return JSONResponse({"ok": False, "mensaje": "No hay CSV en data/. Ejecutar pipeline.py primero."})
    return detectar_anomalias(senadores, senadores_ant, dieta, fecha_datos)


@app.get("/ia/resumen")
def ia_resumen():
    """
    Agente autónomo (parte 2): además de los hallazgos, si hay
    ANTHROPIC_API_KEY configurada le pide a Claude un resumen ejecutivo en
    lenguaje natural. Es el mismo análisis que corre scripts/agente_monitor.py
    en el workflow diario, expuesto para verlo on-demand desde el dashboard.
    """
    senadores, senadores_ant, dieta, fecha_datos = _cargar_datos_para_ia()
    if senadores is None:
        return JSONResponse({"ok": False, "mensaje": "No hay CSV en data/. Ejecutar pipeline.py primero."})
    return resumen_diario(senadores, senadores_ant, dieta, fecha_datos)


# ── Chat interactivo del agente (tool-calling) ────────────────────────────────
# Widget "🤖 Agente" del dashboard: preguntas puntuales en lenguaje natural
# ("¿cómo viene tal senador?", "¿qué bloque tiene más bancas?", "¿cuál es la
# dieta actual?"). Reutiliza los mismos datos que el resto de /ia/*, sin
# recalcular nada — cada tool es de solo lectura sobre los CSV/JSON ya
# generados por el pipeline diario. Rate-limit por IP para controlar costo.
CHAT_RATE_LIMIT_DIARIO = int(os.getenv("CHAT_RATE_LIMIT_DIARIO", "30"))
_chat_contador: dict = {}  # ip -> (fecha_iso, cantidad_hoy)


def _chat_rate_limit_ok(ip: str) -> bool:
    hoy = datetime.date.today().isoformat()
    fecha, cantidad = _chat_contador.get(ip, (hoy, 0))
    if fecha != hoy:
        fecha, cantidad = hoy, 0
    if cantidad >= CHAT_RATE_LIMIT_DIARIO:
        _chat_contador[ip] = (fecha, cantidad)
        return False
    _chat_contador[ip] = (fecha, cantidad + 1)
    return True


def _cargar_partidos_para_chat() -> list:
    import pandas as pd
    csv = _latest_csv("reporte_partido_senado_*.csv")
    if not csv:
        return []
    df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
    return df.to_dict("records")


def _cargar_provincias_para_chat() -> list:
    import pandas as pd
    csv = _latest_csv("reporte_provincial_senado_*.csv")
    if not csv:
        return []
    df = pd.read_csv(csv, encoding="utf-8-sig", on_bad_lines="skip")
    return df.to_dict("records")


def _tool_buscar_senadores(query: str) -> dict:
    senadores, _, _, _ = _cargar_datos_para_ia()
    if not senadores:
        return {"error": "No hay CSV de senadores cargado en data/."}
    q = (query or "").strip().lower()
    resultados = [
        s for s in senadores
        if q in str(s.get("nombre", "")).lower()
        or q in str(s.get("provincia", "")).lower()
        or q in str(s.get("partido", "")).lower()
    ]
    return {"total": len(resultados), "senadores": resultados[:10]}


def _tool_buscar_partido(query: str) -> dict:
    partidos = _cargar_partidos_para_chat()
    q = (query or "").strip().lower()
    resultados = [p for p in partidos if q in str(p.get("partido", "")).lower()]
    return {"total": len(resultados), "partidos": resultados[:10]}


def _tool_buscar_provincia(query: str) -> dict:
    provincias = _cargar_provincias_para_chat()
    q = (query or "").strip().lower()
    resultados = [p for p in provincias if q in str(p.get("provincia", "")).lower()]
    return {"total": len(resultados), "provincias": resultados[:10]}


def _tool_consultar_dieta() -> dict:
    import json as _json
    dieta_path = Path(__file__).parent.parent / "dieta.json"
    if not dieta_path.exists():
        return {"error": "dieta.json no disponible en este entorno."}
    try:
        return _json.load(open(dieta_path, encoding="utf-8"))
    except Exception as e:
        return {"error": f"No se pudo leer dieta.json: {e}"}


def _tool_consultar_anomalias() -> dict:
    senadores, senadores_ant, dieta, fecha_datos = _cargar_datos_para_ia()
    if senadores is None:
        return {"error": "No hay CSV de senadores en data/."}
    return detectar_anomalias(senadores, senadores_ant, dieta, fecha_datos)


TOOLS_SCHEMA_CHAT = [
    {
        "name": "buscar_senadores",
        "description": "Busca senadores por nombre, provincia o partido (coincidencia parcial, "
                        "no requiere el nombre completo). Devuelve hasta 10 resultados con "
                        "participación en votaciones, votos afirmativos/negativos, abstenciones y ausencias.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Texto a buscar"}},
            "required": ["query"],
        },
    },
    {
        "name": "buscar_partido",
        "description": "Busca bloques/partidos políticos del Senado por nombre (coincidencia parcial). "
                        "Devuelve bancas, participación promedio y votos agregados del bloque.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Nombre del bloque o partido"}},
            "required": ["query"],
        },
    },
    {
        "name": "buscar_provincia",
        "description": "Busca datos agregados por provincia (coincidencia parcial). Devuelve cantidad "
                        "de senadores registrados, partidos representados y participación promedio.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Nombre de la provincia"}},
            "required": ["query"],
        },
    },
    {
        "name": "consultar_dieta",
        "description": "Devuelve los datos oficiales más recientes de la dieta (sueldo) parlamentaria "
                        "de los senadores, parseados del recibo oficial en PDF de senado.gob.ar.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "consultar_anomalias",
        "description": "Devuelve los hallazgos del agente autónomo de monitoreo (participación crítica, "
                        "datos desactualizados, composición incompleta, outliers) de la corrida más reciente.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _ejecutar_tool_chat(nombre: str, args: dict):
    args = args or {}
    if nombre == "buscar_senadores":
        return _tool_buscar_senadores(args.get("query", ""))
    if nombre == "buscar_partido":
        return _tool_buscar_partido(args.get("query", ""))
    if nombre == "buscar_provincia":
        return _tool_buscar_provincia(args.get("query", ""))
    if nombre == "consultar_dieta":
        return _tool_consultar_dieta()
    if nombre == "consultar_anomalias":
        return _tool_consultar_anomalias()
    return {"error": f"Herramienta desconocida: {nombre}"}


SYSTEM_PROMPT_CHAT = (
    "Sos un asistente de transparencia legislativa del Senado de la Nación Argentina, "
    "disponible en el dashboard público del Monitor Legislativo. Respondés en español "
    "rioplatense, de forma breve y concreta (6-8 líneas salvo que el usuario pida una lista). "
    "Tenés herramientas de solo lectura para buscar senadores, partidos, provincias, la dieta "
    "parlamentaria oficial y los hallazgos del agente de monitoreo — usalas siempre que la "
    "pregunta involucre un dato concreto, nunca inventes cifras ni nombres. No acusás a nadie "
    "de mal desempeño: describís lo que dicen los datos y, si corresponde, qué convendría "
    "contextualizar antes de sacar conclusiones. Si no encontrás el dato pedido, decilo con "
    "claridad en vez de especular."
)


class ChatIn(BaseModel):
    mensaje: str
    historial: list = []


@app.post("/ia/chat")
def ia_chat(req: ChatIn, request: Request):
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "desconocido"))
    if not _chat_rate_limit_ok(ip):
        return JSONResponse(status_code=429, content={
            "ok": False,
            "error": f"Límite diario de {CHAT_RATE_LIMIT_DIARIO} consultas alcanzado. Probá de nuevo mañana.",
        })
    mensaje = (req.mensaje or "").strip()
    if not mensaje:
        return JSONResponse(status_code=400, content={"ok": False, "error": "El mensaje está vacío."})
    resultado = chat_con_tools(
        mensaje, req.historial, TOOLS_SCHEMA_CHAT, _ejecutar_tool_chat, SYSTEM_PROMPT_CHAT,
    )
    return JSONResponse({"ok": True, **resultado})


# ── Raíz y salud ──────────────────────────────────────────────────────────────
_BASE = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
_BASE = f"https://{_BASE}" if _BASE else "https://monitorlegistativosenadores-production.up.railway.app"


@app.get("/")
def raiz():
    """Redirige al dashboard principal."""
    return RedirectResponse(url="/dashboard/senado.html", status_code=302)


@app.get("/info")
def info():
    csv = _latest_csv("senadores_*.csv")
    return {
        "proyecto": "Monitor Legislativo — Senado Nacional Argentina",
        "version": "1.0.0",
        "url_base": _BASE,
        "db_configurada": bool(_DB_URL),
        "csv_disponible": csv.name if csv else None,
        "endpoints": {
            "dashboard":          f"{_BASE}/dashboard/senado.html",
            "indicadores":        f"{_BASE}/dashboard/indicadores.html",
            "senadores":          f"{_BASE}/senado/senadores",
            "reporte_partido":    f"{_BASE}/senado/reporte-partido",
            "reporte_provincial": f"{_BASE}/senado/reporte-provincial",
            "db_senadores":       f"{_BASE}/db/senadores",
            "db_fechas":          f"{_BASE}/db/fechas",
            "ia_status":          f"{_BASE}/ia/status",
            "ia_anomalias":       f"{_BASE}/ia/anomalias",
            "ia_resumen":         f"{_BASE}/ia/resumen",
            "ia_chat":            f"{_BASE}/ia/chat",
            "salud":              f"{_BASE}/salud",
            "docs":               f"{_BASE}/docs",
        },
    }


@app.get("/salud")
def salud():
    csv = _latest_csv("senadores_*.csv")
    return {
        "status": "ok",
        "csv": csv.name if csv else None,
        "db_configurada": bool(_DB_URL),
        "dashboard": _DASHBOARD.exists(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.run_senado:app", host="0.0.0.0", port=8000, reload=True)
