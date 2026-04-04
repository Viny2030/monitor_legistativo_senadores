"""
scripts/actualizar_versiones_taq_senado.py
==========================================
Descarga el listado de versiones taquigráficas desde la API oficial del Senado.

NOTA: El endpoint devuelve sesiones con URL de descarga, NO oradores.
      Por eso este script calcula métricas por SESIÓN, no por senador:
        - total de versiones disponibles
        - sesiones del año actual
        - tipos de sesión (ordinaria, especial, asamblea)

  1. data/versiones_taq_{fecha}.csv  →  fecha | tipo | nro_sesion | nro_reunion | url

  2. Inyecta bloque JS en dashboard/indicadores_senadores.html
     entre marcadores // TAQUIGRAFICAS:START  /  // TAQUIGRAFICAS:END

     var TAQUIGRAFICAS_DATA = {
       total: N,
       anio_actual: N,
       ordinarias: N,
       especiales: N,
       asambleas: N,
       ultima_fecha: "DD-MM-YYYY"
     };

Fuente:
  https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoVersionesTac/json

Uso:
  python scripts/actualizar_versiones_taq_senado.py
"""

import os
import re
import json
import time
import requests
import pandas as pd
from datetime import date, datetime

URL  = "https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoVersionesTac/json"
HDRS = {"User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)", "Accept": "application/json"}

DATA_DIR     = "data"
HTML_PATH    = "dashboard/indicadores_senadores.html"
MARKER_START = "// TAQUIGRAFICAS:START"
MARKER_END   = "// TAQUIGRAFICAS:END"
HOY          = date.today().isoformat()
ANIO_ACTUAL  = date.today().year


def _limpiar_json(texto: str) -> str:
    """
    El JSON del Senado tiene trailing commas antes de } y ].
    Ejemplo: {"campo": "valor",} → {"campo": "valor"}
    """
    # Eliminar comas antes de } o ]
    texto = re.sub(r",\s*([}\]])", r"\1", texto)
    return texto


def descargar():
    print("📥 Descargando versiones taquigráficas...")
    for i in range(3):
        try:
            r = requests.get(URL, headers=HDRS, timeout=30)
            if r.status_code == 200:
                texto_limpio = _limpiar_json(r.text)
                data = json.loads(texto_limpio)
                rows = data.get("table", {}).get("rows", [])
                print(f"  ✅ {len(rows)} versiones recibidas")
                return rows
            print(f"  ⚠️  HTTP {r.status_code} — reintento {i+1}/3...")
        except Exception as e:
            print(f"  ❌ {e} — reintento {i+1}/3...")
        time.sleep(5)
    return []


def procesar(rows: list) -> dict:
    """
    Calcula métricas agregadas por sesión.
    Campos del JSON: FECHA DE SESION, TIPO DE SESION, NRO DE SESION,
                     NRO DE REUNION, URL VESION TAQUIGRAFICA
    """
    total     = len(rows)
    anio_act  = 0
    ordinarias = 0
    especiales = 0
    asambleas  = 0
    ultima     = ""

    for r in rows:
        fecha = str(r.get("FECHA DE SESION", "")).strip()
        tipo  = str(r.get("TIPO DE SESION", "")).strip().upper()

        # Contar por año actual (formato DD-MM-YYYY)
        try:
            anio = int(fecha.split("-")[2])
            if anio == ANIO_ACTUAL:
                anio_act += 1
        except Exception:
            pass

        # Contar por tipo
        if "ORDINARIA" in tipo:
            ordinarias += 1
        elif "ESPECIAL" in tipo:
            especiales += 1
        elif "ASAMBLEA" in tipo:
            asambleas += 1

        # Última fecha (la primera del listado suele ser la más reciente)
        if not ultima and fecha:
            ultima = fecha

    return {
        "total":        total,
        "anio_actual":  anio_act,
        "ordinarias":   ordinarias,
        "especiales":   especiales,
        "asambleas":    asambleas,
        "ultima_fecha": ultima,
    }


def guardar_csv(rows: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"versiones_taq_{HOY}.csv")
    df = pd.DataFrame([{
        "fecha":      r.get("FECHA DE SESION", ""),
        "tipo":       r.get("TIPO DE SESION", ""),
        "nro_sesion": r.get("NRO DE SESION", ""),
        "nro_reunion":r.get("NRO DE REUNION", ""),
        "url":        r.get("URL VESION TAQUIGRAFICA", ""),
    } for r in rows])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  💾 {path} ({os.path.getsize(path):,} bytes)")


def construir_bloque(datos: dict, fecha: str) -> str:
    js = (
        f"var TAQUIGRAFICAS_DATA = {{\n"
        f"  total: {datos['total']},\n"
        f"  anio_actual: {datos['anio_actual']},\n"
        f"  ordinarias: {datos['ordinarias']},\n"
        f"  especiales: {datos['especiales']},\n"
        f"  asambleas: {datos['asambleas']},\n"
        f"  ultima_fecha: \"{datos['ultima_fecha']}\"\n"
        f"}};"
    )
    return f"{MARKER_START}\n// Actualizado {fecha} — no editar a mano\n{js}\n{MARKER_END}"


def actualizar_html(nuevo_bloque: str) -> bool:
    if not os.path.exists(HTML_PATH):
        print(f"  ❌ No encontrado: {HTML_PATH}")
        return False
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()
    i0 = contenido.find(MARKER_START)
    i1 = contenido.find(MARKER_END)
    if i0 == -1 or i1 == -1:
        print(f"  ⚠️  Marcadores no encontrados en {HTML_PATH}")
        return False
    if contenido[i0: i1 + len(MARKER_END)] == nuevo_bloque:
        print("  ℹ️  Sin cambios.")
        return False
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(contenido[:i0] + nuevo_bloque + contenido[i1 + len(MARKER_END):])
    print(f"  ✅ {HTML_PATH} actualizado ({os.path.getsize(HTML_PATH):,} bytes)")
    return True


def main():
    print("=" * 55)
    print("🏛️  Monitor Senado — Versiones Taquigráficas")
    print(f"📅  Fecha: {HOY}")
    print("=" * 55)

    rows = descargar()
    if not rows:
        print("❌ Sin datos. Abortando.")
        return

    datos = procesar(rows)

    print("\n💾 Guardando CSV...")
    guardar_csv(rows)

    print(f"\n📊 Resumen versiones taquigráficas:")
    print(f"   Total histórico         : {datos['total']}")
    print(f"   Año {ANIO_ACTUAL}               : {datos['anio_actual']}")
    print(f"   Ordinarias              : {datos['ordinarias']}")
    print(f"   Especiales              : {datos['especiales']}")
    print(f"   Asambleas               : {datos['asambleas']}")
    print(f"   Última sesión           : {datos['ultima_fecha']}")

    print(f"\n📄 Actualizando {HTML_PATH}...")
    actualizar_html(construir_bloque(datos, HOY))

    print("\n✅ Listo")


if __name__ == "__main__":
    main()