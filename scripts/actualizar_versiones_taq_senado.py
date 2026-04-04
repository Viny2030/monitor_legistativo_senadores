"""
scripts/actualizar_versiones_taq_senado.py
==========================================
Descarga el listado de versiones taquigráficas desde la API JSON oficial
del Senado y genera dos outputs:

  1. data/versiones_taq_{fecha}.csv
       nombre | intervenciones | sesiones_distintas | primera | ultima

  2. Inyecta el bloque JS en dashboard/indicadores_senadores.html
       entre los marcadores:
         // TAQUIGRAFICAS:START
         // TAQUIGRAFICAS:END

El bloque inyectado expone:
  var TAQUIGRAFICAS_DATA = [
    {nombre:"...", intervenciones: N, sesiones: N},
    ...
  ];

Uso:
  python scripts/actualizar_versiones_taq_senado.py

Fuente:
  https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoVersionesTac/json
"""

import os
import glob
import json
import requests
import pandas as pd
from datetime import date, datetime

# ── Config ────────────────────────────────────────────────────────────────────
URL_TAQ = (
    "https://www.senado.gob.ar/micrositios/DatosAbiertos"
    "/ExportarListadoVersionesTac/json"
)
HEADERS = {
    "User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)",
    "Accept": "application/json",
}

DATA_DIR  = "data"
HTML_PATH = "dashboard/indicadores_senadores.html"

MARKER_START = "// TAQUIGRAFICAS:START"
MARKER_END   = "// TAQUIGRAFICAS:END"

HOY      = date.today().isoformat()
HOY_DT   = datetime.today()
ANIO_ACT = HOY_DT.year


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

def descargar_versiones() -> list:
    """
    Descarga el JSON de versiones taquigráficas.
    Estructura esperada (cada ítem puede variar — la API del Senado
    devuelve objetos con campos de sesión y lista de oradores):
      {
        "fecha": "2025-11-12",
        "periodo": 143,
        "reunion": 7,
        "oradores": [
          {"nombre": "APELLIDO, Nombre", ...},
          ...
        ]
      }
    O bien puede ser una lista plana de intervenciones:
      {
        "fecha": "...",
        "nombre": "APELLIDO, Nombre",
        ...
      }
    El script detecta ambos formatos.
    """
    print(f"📥 Descargando versiones taquigráficas desde API oficial...")
    data = _get_con_reintento(URL_TAQ)
    if not data:
        print("  ❌ No se pudo obtener el JSON de versiones taquigráficas")
        return []
    items = data if isinstance(data, list) else data.get("data", data.get("items", []))
    print(f"  ✅ {len(items)} registros recibidos")
    return items


# ── 2. Detectar formato y normalizar ─────────────────────────────────────────

def normalizar_versiones(items: list) -> list:
    """
    Devuelve una lista de dicts con al menos:
      nombre | fecha | periodo
    independientemente del formato original de la API.
    """
    if not items:
        return []

    primer = items[0] if items else {}

    # Formato A: cada ítem ES una intervención individual
    if "nombre" in primer:
        return [
            {
                "nombre":  str(item.get("nombre", "")).strip(),
                "fecha":   str(item.get("fecha", "")).strip(),
                "periodo": int(item.get("periodo", 0)),
            }
            for item in items
            if item.get("nombre")
        ]

    # Formato B: cada ítem es una sesión con lista de oradores
    if "oradores" in primer or "senadores" in primer:
        filas = []
        for item in items:
            fecha   = str(item.get("fecha", "")).strip()
            periodo = int(item.get("periodo", 0))
            oradores = item.get("oradores", item.get("senadores", []))
            for o in oradores:
                nombre = str(o.get("nombre", o.get("senador", ""))).strip()
                if nombre:
                    filas.append({"nombre": nombre, "fecha": fecha, "periodo": periodo})
        return filas

    # Formato desconocido: intentar extraer cualquier campo que parezca nombre
    print("  ⚠️  Formato desconocido — intentando detección automática de campos")
    claves_nombre = [k for k in primer if any(x in k.lower() for x in ["nombre", "senador", "orador"])]
    claves_fecha  = [k for k in primer if "fecha" in k.lower()]
    if not claves_nombre:
        print("  ❌ No se encontró campo de nombre en el JSON")
        return []
    filas = []
    for item in items:
        nombre = str(item.get(claves_nombre[0], "")).strip()
        fecha  = str(item.get(claves_fecha[0], "")) if claves_fecha else ""
        if nombre:
            filas.append({"nombre": nombre, "fecha": fecha, "periodo": 0})
    return filas


# ── 3. Agregar por senador ────────────────────────────────────────────────────

def agregar_por_senador(filas: list) -> pd.DataFrame:
    """
    Agrupa las intervenciones por senador y calcula:
      - intervenciones: cantidad total
      - sesiones_distintas: fechas únicas en las que habló
      - primera / ultima: fechas extremas
    """
    if not filas:
        return pd.DataFrame(columns=["nombre", "intervenciones", "sesiones_distintas", "primera", "ultima"])

    df = pd.DataFrame(filas)

    # Filtrar período actual si hay columna periodo
    if "periodo" in df.columns and df["periodo"].max() > 0:
        periodo_max = df["periodo"].max()
        df = df[df["periodo"] == periodo_max].copy()
        print(f"  ℹ️  Filtrado al período {periodo_max} ({len(df)} intervenciones)")

    agg = (
        df.groupby("nombre")
        .agg(
            intervenciones    = ("nombre", "count"),
            sesiones_distintas = ("fecha", "nunique"),
            primera           = ("fecha", "min"),
            ultima            = ("fecha", "max"),
        )
        .reset_index()
        .sort_values("intervenciones", ascending=False)
        .reset_index(drop=True)
    )

    print(f"  ✅ {len(agg)} senadores con intervenciones taquigráficas")
    return agg


# ── 4. Cruzar con nómina CSV ──────────────────────────────────────────────────

def cruzar_con_nomina(df_taq: pd.DataFrame) -> pd.DataFrame:
    csv_sen = _csv_mas_reciente("senadores_*.csv")
    if not csv_sen:
        print("  ℹ️  Sin CSV de nómina — se omiten provincia/bloque")
        return df_taq

    df_nom = pd.read_csv(csv_sen, encoding="utf-8-sig")

    def _apellido(nombre: str) -> str:
        return nombre.split(",")[0].strip().lower() if isinstance(nombre, str) else ""

    df_taq = df_taq.copy()
    df_nom = df_nom.copy()
    df_taq["_key"] = df_taq["nombre"].apply(_apellido)
    df_nom["_key"] = df_nom["nombre"].apply(_apellido)

    df_merged = df_taq.merge(
        df_nom[["_key", "provincia", "partido_normalizado"]].rename(
            columns={"partido_normalizado": "bloque"}
        ),
        on="_key",
        how="left",
    ).drop(columns=["_key"])

    return df_merged


# ── 5. Guardar CSV ────────────────────────────────────────────────────────────

def guardar_csv(df: pd.DataFrame) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"versiones_taq_{HOY}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  💾 {path} ({os.path.getsize(path):,} bytes)")
    return path


# ── 6. Construir bloque JS ────────────────────────────────────────────────────

def construir_bloque_js(df: pd.DataFrame, fecha: str) -> str:
    lineas = []
    for _, row in df.iterrows():
        nombre      = json.dumps(str(row.get("nombre", "")).strip(), ensure_ascii=False)
        interv      = int(row.get("intervenciones", 0))
        sesiones    = int(row.get("sesiones_distintas", 0))
        lineas.append(
            f"  {{nombre:{nombre},intervenciones:{interv},sesiones:{sesiones}}}"
        )

    array_js = "var TAQUIGRAFICAS_DATA = [\n" + ",\n".join(lineas) + "\n];"

    return (
        f"{MARKER_START}\n"
        f"// Versiones taquigráficas actualizadas automáticamente el {fecha} — no editar a mano\n"
        f"{array_js}\n"
        f"{MARKER_END}"
    )


# ── 7. Inyectar en HTML ───────────────────────────────────────────────────────

def actualizar_html(nuevo_bloque: str) -> bool:
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
        print("  ℹ️  TAQUIGRAFICAS_DATA ya estaba actualizado. Sin cambios.")
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
    print("🏛️  Monitor Senado — Actualizando Versiones Taquigráficas")
    print(f"📅  Fecha: {HOY}")
    print("=" * 55)

    # 1. Descargar
    items = descargar_versiones()
    if not items:
        print("❌ Sin datos de versiones taquigráficas. Abortando.")
        return

    # 2. Normalizar formato
    filas = normalizar_versiones(items)
    if not filas:
        print("❌ No se pudo normalizar el JSON. Abortando.")
        return

    # 3. Agregar por senador
    df = agregar_por_senador(filas)
    if df.empty:
        print("❌ DataFrame vacío. Abortando.")
        return

    # 4. Cruzar con nómina
    df = cruzar_con_nomina(df)

    # 5. Guardar CSV
    print("\n💾 Guardando CSV...")
    guardar_csv(df)

    # 6. Resumen consola
    print(f"\n📊 Resumen versiones taquigráficas:")
    print(f"   Senadores con intervenciones : {len(df)}")
    print(f"   Promedio intervenciones      : {df['intervenciones'].mean():.1f}")
    print(f"   Máximo                       : {df['intervenciones'].max()} ({df.iloc[0]['nombre']})")
    print(f"\n🏆 Top 10 senadores por intervenciones:")
    cols = ["nombre", "intervenciones", "sesiones_distintas"]
    if "provincia" in df.columns:
        cols.insert(1, "provincia")
    print(df[cols].head(10).to_string(index=False))

    # 7. Inyectar en HTML
    print(f"\n📄 Actualizando {HTML_PATH}...")
    bloque = construir_bloque_js(df, HOY)
    actualizar_html(bloque)

    print("\n✅ Versiones taquigráficas actualizadas correctamente")


if __name__ == "__main__":
    main()