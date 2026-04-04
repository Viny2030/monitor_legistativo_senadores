"""
scripts/actualizar_comisiones_senado.py
========================================
Descarga el listado de comisiones desde la API JSON oficial del Senado
y genera dos outputs:

  1. data/comisiones_{fecha}.csv  →  nombre | tipo

  2. Inyecta bloque JS en dashboard/indicadores_senadores.html
     entre marcadores // COMISIONES:START  /  // COMISIONES:END

     var COMISIONES_DATA = {
       total: 48,
       unicameral_permanente: N,
       bicameral_permanente: N,
       bicameral_especial: N,
       lista: [{nombre:"...", tipo:"..."}, ...]
     };

Fuente:
  https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas

Uso:
  python scripts/actualizar_comisiones_senado.py
"""

import os
import json
import time
import requests
import pandas as pd
from datetime import date

URL  = "https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas"
HDRS = {"User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)", "Accept": "application/json"}

DATA_DIR     = "data"
HTML_PATH    = "dashboard/indicadores_senadores.html"
MARKER_START = "// COMISIONES:START"
MARKER_END   = "// COMISIONES:END"
HOY          = date.today().isoformat()


def _get(url, intentos=3, espera=5):
    for i in range(intentos):
        try:
            r = requests.get(url, headers=HDRS, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"  ⚠️  HTTP {r.status_code} — reintento {i+1}/{intentos}...")
        except Exception as e:
            print(f"  ❌ {e} — reintento {i+1}/{intentos}...")
        time.sleep(espera)
    return None


def descargar():
    print("📥 Descargando comisiones...")
    data = _get(URL)
    if not data:
        return []
    rows = data.get("table", {}).get("rows", [])
    print(f"  ✅ {len(rows)} comisiones")
    return rows


def procesar(rows):
    conteos = {}
    lista = []
    for r in rows:
        nombre = str(r.get("NOMBRE", "")).strip()
        tipo   = str(r.get("TIPO_COMISION", "")).strip().upper()
        conteos[tipo] = conteos.get(tipo, 0) + 1
        lista.append({"nombre": nombre, "tipo": tipo})
    return {
        "total":                 len(rows),
        "unicameral_permanente": conteos.get("UNICAMERAL PERMANENTE", 0),
        "bicameral_permanente":  conteos.get("BICAMERAL PERMANENTE", 0),
        "bicameral_especial":    conteos.get("BICAMERAL ESPECIAL", 0),
        "lista":                 lista,
    }


def guardar_csv(lista):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"comisiones_{HOY}.csv")
    pd.DataFrame(lista).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  💾 {path} ({os.path.getsize(path):,} bytes)")


def construir_bloque(datos, fecha):
    lista_js = json.dumps(datos["lista"], ensure_ascii=False)
    js = (
        f"var COMISIONES_DATA = {{\n"
        f"  total: {datos['total']},\n"
        f"  unicameral_permanente: {datos['unicameral_permanente']},\n"
        f"  bicameral_permanente: {datos['bicameral_permanente']},\n"
        f"  bicameral_especial: {datos['bicameral_especial']},\n"
        f"  lista: {lista_js}\n"
        f"}};"
    )
    return f"{MARKER_START}\n// Actualizado {fecha} — no editar a mano\n{js}\n{MARKER_END}"


def actualizar_html(nuevo_bloque):
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
    print("🏛️  Monitor Senado — Actualizando Comisiones")
    print(f"📅  Fecha: {HOY}")
    print("=" * 55)

    rows = descargar()
    if not rows:
        print("❌ Sin datos. Abortando.")
        return

    datos = procesar(rows)

    print("\n💾 Guardando CSV...")
    guardar_csv(datos["lista"])

    print(f"\n📊 Resumen:")
    print(f"   Total                   : {datos['total']}")
    print(f"   Unicamerales permanentes: {datos['unicameral_permanente']}")
    print(f"   Bicamerales permanentes : {datos['bicameral_permanente']}")
    print(f"   Bicamerales especiales  : {datos['bicameral_especial']}")

    print(f"\n📄 Actualizando {HTML_PATH}...")
    actualizar_html(construir_bloque(datos, HOY))

    print("\n✅ Listo")


if __name__ == "__main__":
    main()