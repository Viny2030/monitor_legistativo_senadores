"""
scripts/actualizar_comisiones_senado.py
========================================
Descarga el listado de comisiones desde la API JSON oficial del Senado
y genera dos outputs:

  1. data/comisiones_{fecha}.csv
       nombre | provincia | bloque | comisiones | comisiones_lista

  2. Inyecta el bloque JS en dashboard/indicadores_senadores.html
       entre los marcadores:
         // COMISIONES:START
         // COMISIONES:END

El bloque inyectado expone:
  var COMISIONES_DATA = [
    {nombre:"...", comisiones: N, lista: ["...", ...]},
    ...
  ];

Uso:
  python scripts/actualizar_comisiones_senado.py

Fuente:
  https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoComisiones/json/todas
"""

import os
import glob
import json
import requests
import pandas as pd
from datetime import date, datetime

# ── Config ────────────────────────────────────────────────────────────────────
URL_COMISIONES = (
    "https://www.senado.gob.ar/micrositios/DatosAbiertos"
    "/ExportarListadoComisiones/json/todas"
)
HEADERS = {
    "User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)",
    "Accept": "application/json",
}

DATA_DIR  = "data"
HTML_PATH = "dashboard/indicadores_senadores.html"

MARKER_START = "// COMISIONES:START"
MARKER_END   = "// COMISIONES:END"

HOY = date.today().isoformat()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _csv_mas_reciente(patron: str) -> str | None:
    archivos = sorted(glob.glob(os.path.join(DATA_DIR, patron)))
    return archivos[-1] if archivos else None


def _get_con_reintento(url: str, intentos: int = 3, espera: int = 5):
    import time
    for i in range(intentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            print(f"  ⚠️  HTTP {resp.status_code} — reintento {i+1}/{intentos}...")
            time.sleep(espera)
        except Exception as e:
            print(f"  ❌ {e} — reintento {i+1}/{intentos}...")
            time.sleep(espera)
    return None


# ── 1. Descarga ───────────────────────────────────────────────────────────────

def descargar_comisiones() -> list:
    """
    Descarga el JSON de comisiones del Senado.
    Estructura esperada (cada ítem):
      {
        "nombre": "Nombre de la comisión",
        "tipo": "Permanente" | "Bicameral" | ...,
        "miembros": [
          {"nombre": "APELLIDO, Nombre", "cargo": "Presidente"|"Vocal"|...},
          ...
        ]
      }
    Devuelve la lista de comisiones o [] si falla.
    """
    print(f"📥 Descargando comisiones desde API oficial...")
    data = _get_con_reintento(URL_COMISIONES)
    if not data:
        print("  ❌ No se pudo obtener el JSON de comisiones")
        return []
    print(f"  ✅ {len(data)} comisiones recibidas")
    return data if isinstance(data, list) else []


# ── 2. Procesar → DataFrame por senador ──────────────────────────────────────

def procesar_comisiones(comisiones: list) -> pd.DataFrame:
    """
    A partir de la lista de comisiones, construye un DataFrame
    con una fila por senador que registra en cuántas y cuáles participa.

    Devuelve columnas: nombre | comisiones | comisiones_lista
    """
    # Acumular: nombre_senador → set de comisiones
    mapa: dict[str, list] = {}

    for com in comisiones:
        nombre_com = str(com.get("nombre", "")).strip()
        tipo_com   = str(com.get("tipo", "")).strip()
        miembros   = com.get("miembros", []) or []

        # Etiquetar tipo en el nombre para claridad
        etiqueta = nombre_com
        if tipo_com and tipo_com.lower() not in nombre_com.lower():
            etiqueta = f"{nombre_com} ({tipo_com})"

        for m in miembros:
            nombre_sen = str(m.get("nombre", "")).strip()
            if not nombre_sen:
                continue
            if nombre_sen not in mapa:
                mapa[nombre_sen] = []
            if etiqueta not in mapa[nombre_sen]:
                mapa[nombre_sen].append(etiqueta)

    if not mapa:
        return pd.DataFrame(columns=["nombre", "comisiones", "comisiones_lista"])

    filas = []
    for nombre, lista in mapa.items():
        filas.append({
            "nombre":           nombre,
            "comisiones":       len(lista),
            "comisiones_lista": lista,
        })

    df = pd.DataFrame(filas).sort_values("comisiones", ascending=False).reset_index(drop=True)
    print(f"  ✅ {len(df)} senadores con al menos 1 comisión")
    return df


# ── 3. Cruzar con nómina CSV ──────────────────────────────────────────────────

def cruzar_con_nomina(df_com: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza los datos de comisiones con el CSV de nómina más reciente
    para agregar provincia y bloque. No es obligatorio — si no hay CSV
    devuelve df_com tal cual.
    """
    csv_sen = _csv_mas_reciente("senadores_*.csv")
    if not csv_sen:
        print("  ℹ️  Sin CSV de nómina para cruzar — se omiten provincia/bloque")
        return df_com

    df_nom = pd.read_csv(csv_sen, encoding="utf-8-sig")

    # Normalizar apellido para cruzar (primer token antes de la coma, minúsculas)
    def _apellido(nombre: str) -> str:
        return nombre.split(",")[0].strip().lower() if isinstance(nombre, str) else ""

    df_com  = df_com.copy()
    df_nom  = df_nom.copy()
    df_com["_key"]  = df_com["nombre"].apply(_apellido)
    df_nom["_key"]  = df_nom["nombre"].apply(_apellido)

    df_merged = df_com.merge(
        df_nom[["_key", "provincia", "partido_normalizado"]].rename(
            columns={"partido_normalizado": "bloque"}
        ),
        on="_key",
        how="left",
    ).drop(columns=["_key"])

    return df_merged


# ── 4. Guardar CSV ────────────────────────────────────────────────────────────

def guardar_csv(df: pd.DataFrame) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"comisiones_{HOY}.csv")
    # Serializar la lista a string para el CSV
    df_csv = df.copy()
    df_csv["comisiones_lista"] = df_csv["comisiones_lista"].apply(
        lambda x: " | ".join(x) if isinstance(x, list) else str(x)
    )
    df_csv.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  💾 {path} ({os.path.getsize(path):,} bytes)")
    return path


# ── 5. Construir bloque JS ────────────────────────────────────────────────────

def construir_bloque_js(df: pd.DataFrame, fecha: str) -> str:
    """
    Genera el bloque JS con var COMISIONES_DATA = [...];
    Cada ítem: {nombre, comisiones, lista}
    """
    lineas = []
    for _, row in df.iterrows():
        nombre     = json.dumps(str(row.get("nombre", "")).strip(), ensure_ascii=False)
        n_com      = int(row.get("comisiones", 0))
        lista_raw  = row.get("comisiones_lista", [])
        if isinstance(lista_raw, str):
            lista_raw = [x.strip() for x in lista_raw.split("|") if x.strip()]
        lista_js   = json.dumps(lista_raw, ensure_ascii=False)
        lineas.append(f"  {{nombre:{nombre},comisiones:{n_com},lista:{lista_js}}}")

    array_js = "var COMISIONES_DATA = [\n" + ",\n".join(lineas) + "\n];"

    return (
        f"{MARKER_START}\n"
        f"// Comisiones actualizadas automáticamente el {fecha} — no editar a mano\n"
        f"{array_js}\n"
        f"{MARKER_END}"
    )


# ── 6. Inyectar en HTML ───────────────────────────────────────────────────────

def actualizar_html(nuevo_bloque: str) -> bool:
    """
    Reemplaza el contenido entre MARKER_START y MARKER_END en el HTML.
    Si los marcadores no existen, imprime instrucciones y retorna False.
    """
    if not os.path.exists(HTML_PATH):
        print(f"  ❌ No se encontró {HTML_PATH}")
        return False

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()

    idx_start = contenido.find(MARKER_START)
    idx_end   = contenido.find(MARKER_END)

    if idx_start == -1 or idx_end == -1:
        print(
            f"\n  ⚠️  Marcadores no encontrados en {HTML_PATH}.\n"
            f"  Agregá manualmente antes del cierre </script>:\n\n"
            f"  {MARKER_START}\n"
            f"  {MARKER_END}\n"
        )
        return False

    bloque_actual = contenido[idx_start: idx_end + len(MARKER_END)]
    if bloque_actual == nuevo_bloque:
        print("  ℹ️  COMISIONES_DATA ya estaba actualizado. Sin cambios.")
        return False

    nuevo_contenido = (
        contenido[:idx_start]
        + nuevo_bloque
        + contenido[idx_end + len(MARKER_END):]
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(nuevo_contenido)

    print(f"  ✅ {HTML_PATH} actualizado ({os.path.getsize(HTML_PATH):,} bytes)")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("🏛️  Monitor Senado — Actualizando Comisiones")
    print(f"📅  Fecha: {HOY}")
    print("=" * 55)

    # 1. Descargar
    comisiones = descargar_comisiones()
    if not comisiones:
        print("❌ Sin datos de comisiones. Abortando.")
        return

    # 2. Procesar
    df = procesar_comisiones(comisiones)
    if df.empty:
        print("❌ DataFrame vacío tras procesar. Abortando.")
        return

    # 3. Cruzar con nómina
    df = cruzar_con_nomina(df)

    # 4. Guardar CSV
    print("\n💾 Guardando CSV...")
    guardar_csv(df)

    # 5. Resumen consola
    print(f"\n📊 Resumen comisiones:")
    print(f"   Senadores con comisiones : {len(df)}")
    print(f"   Promedio por senador     : {df['comisiones'].mean():.1f}")
    print(f"   Máximo                   : {df['comisiones'].max()} ({df.iloc[0]['nombre']})")
    print(f"\n🏆 Top 10 senadores por nº de comisiones:")
    cols = ["nombre", "comisiones"]
    if "provincia" in df.columns:
        cols.insert(1, "provincia")
    print(df[cols].head(10).to_string(index=False))

    # 6. Inyectar en HTML
    print(f"\n📄 Actualizando {HTML_PATH}...")
    bloque = construir_bloque_js(df, HOY)
    actualizar_html(bloque)

    print("\n✅ Comisiones actualizadas correctamente")


if __name__ == "__main__":
    main()