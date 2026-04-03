"""
scripts/actualizar_fallback_senado.py
=====================================
Lee el CSV de senadores más reciente generado por scraper_senadores.py
y reemplaza el bloque usarFallback() en dashboard/senado.html con los
datos actualizados.

REGLA: no modifica NINGUNA otra parte del HTML.
Solo reemplaza el contenido entre los marcadores:
  // FALLBACK:START
  ...
  // FALLBACK:END

Uso:
  python scripts/actualizar_fallback_senado.py
"""

import os
import glob
import json
import ast
import pandas as pd
from datetime import date

# ── Rutas ─────────────────────────────────────────────────────────────────────
DATA_DIR   = "data"
HTML_PATH  = "dashboard/senado.html"

MARKER_START = "// FALLBACK:START"
MARKER_END   = "// FALLBACK:END"

HOY = date.today().isoformat()


def _csv_mas_reciente(patron: str) -> str | None:
    """Devuelve la ruta del CSV más reciente que coincide con el patrón."""
    archivos = sorted(glob.glob(os.path.join(DATA_DIR, patron)))
    return archivos[-1] if archivos else None


def _format_valor(v) -> str:
    """Serializa un valor Python a JS literal."""
    if v is None or (isinstance(v, float) and str(v) == 'nan'):
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return str(v)
    # string → escapar comillas
    return json.dumps(str(v), ensure_ascii=False)


def _df_senadores_a_js(df: pd.DataFrame) -> str:
    """Convierte el DataFrame de senadores al array JS para SENADORES_DATA."""
    lineas = []
    for _, row in df.iterrows():
        campos = {
            "id":                _format_valor(row.get("id")),
            "nombre":            _format_valor(row.get("nombre")),
            "provincia":         _format_valor(row.get("provincia")),
            "partido":           _format_valor(row.get("partido_normalizado", row.get("partido"))),
            "rol_provincial":    _format_valor(row.get("rol_provincial")),
            "participation_pct": _format_valor(row.get("participation_pct", 0.0)),
            "votos_afirmativos": _format_valor(int(row.get("votos_afirmativos", 0))),
            "votos_negativos":   _format_valor(int(row.get("votos_negativos", 0))),
            "ausencias":         _format_valor(int(row.get("ausencias", 0))),
            "abstenciones":      _format_valor(int(row.get("abstenciones", 0))),
            "votos_total":       _format_valor(int(row.get("votos_total", 0))),
            "foto":              _format_valor(row.get("foto")),
            "email":             _format_valor(row.get("email")),
            "telefono":          _format_valor(row.get("telefono")),
            "fuente":            "'fallback'",
        }
        pares = ", ".join(f"{k}:{v}" for k, v in campos.items())
        lineas.append(f"    {{ {pares} }}")
    return "  [\n" + ",\n".join(lineas) + "\n  ].sort((a,b) => (b.participation_pct || 0) - (a.participation_pct || 0))"


def _df_partidos_a_js(df: pd.DataFrame) -> str:
    """Convierte el DataFrame de partidos al array JS para PARTIDOS_DATA."""
    lineas = []
    col_partido = "partido" if "partido" in df.columns else "partido_normalizado"
    for _, row in df.iterrows():
        campos = {
            "partido":           _format_valor(row.get(col_partido)),
            "bancas":            _format_valor(int(row.get("bancas", 0))),
            "participation_pct": _format_valor(row.get("participation_pct", 0.0)),
            "'Mayoría'":         _format_valor(int(row.get("Mayoría", 0))),
            "'Primera Minoría'": _format_valor(int(row.get("Primera Minoría", 0))),
            "votos_afirmativos": _format_valor(int(row.get("votos_afirmativos", 0))),
            "votos_negativos":   _format_valor(int(row.get("votos_negativos", 0))),
            "abstenciones":      _format_valor(int(row.get("abstenciones", 0))),
        }
        pares = ", ".join(f"{k}:{v}" for k, v in campos.items())
        lineas.append(f"    {{ {pares} }}")
    return "  [\n" + ",\n".join(lineas) + "\n  ]"


def _df_provincial_a_js(df: pd.DataFrame) -> str:
    """Convierte el DataFrame provincial al array JS para PROVINCIAL_DATA."""
    lineas = []
    for _, row in df.iterrows():
        campos = {
            "provincia":         _format_valor(row.get("provincia")),
            "senadores":         _format_valor(int(row.get("senadores", 0))),
            "participation_pct": _format_valor(row.get("participation_pct", 0.0)),
            "votos_total":       _format_valor(int(row.get("votos_total", 0))),
            "partidos":          _format_valor(row.get("partidos")),
            "'Mayoría'":         _format_valor(int(row.get("Mayoría", 0))),
            "'Primera Minoría'": _format_valor(int(row.get("Primera Minoría", 0))),
        }
        pares = ", ".join(f"{k}:{v}" for k, v in campos.items())
        lineas.append(f"    {{ {pares} }}")
    return "  [\n" + ",\n".join(lineas) + "\n  ]"


def construir_bloque(df_sen: pd.DataFrame,
                     df_part: pd.DataFrame,
                     df_prov: pd.DataFrame,
                     fecha: str) -> str:
    """Genera el bloque JS completo que reemplazará el fallback actual."""
    sen_js  = _df_senadores_a_js(df_sen)
    part_js = _df_partidos_a_js(df_part)
    prov_js = _df_provincial_a_js(df_prov)

    return (
        f"{MARKER_START}\n"
        f"  // Datos generados automáticamente el {fecha} — no editar a mano\n"
        f"  PARTIDOS_DATA = {part_js};\n\n"
        f"  PROVINCIAL_DATA = {prov_js};\n\n"
        f"  // FALLBACK: {len(df_sen)} senadores reales (CSV {fecha})"
        f" — usado cuando la API no responde\n"
        f"  SENADORES_DATA = {sen_js};\n"
        f"{MARKER_END}"
    )


def actualizar_html(nuevo_bloque: str) -> bool:
    """
    Reemplaza el contenido entre MARKER_START y MARKER_END en el HTML.
    Devuelve True si hubo cambio, False si el contenido era idéntico.
    """
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()

    idx_start = contenido.find(MARKER_START)
    idx_end   = contenido.find(MARKER_END)

    if idx_start == -1 or idx_end == -1:
        raise RuntimeError(
            f"No se encontraron los marcadores '{MARKER_START}' / '{MARKER_END}' "
            f"en {HTML_PATH}.\n"
            "Asegurate de agregar los marcadores manualmente alrededor del "
            "bloque usarFallback() en senado.html."
        )

    bloque_actual = contenido[idx_start : idx_end + len(MARKER_END)]
    if bloque_actual == nuevo_bloque:
        print("ℹ️  El fallback ya estaba actualizado. Sin cambios.")
        return False

    nuevo_contenido = (
        contenido[:idx_start]
        + nuevo_bloque
        + contenido[idx_end + len(MARKER_END):]
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(nuevo_contenido)

    return True


def main():
    print("=" * 55)
    print("🔄 Actualizando fallback en senado.html")
    print(f"📅 Fecha: {HOY}")
    print("=" * 55)

    # ── 1. Cargar CSVs más recientes ──────────────────────────────────────────
    csv_sen  = _csv_mas_reciente("senadores_*.csv")
    csv_part = _csv_mas_reciente("reporte_partido_senado_*.csv")
    csv_prov = _csv_mas_reciente("reporte_provincial_senado_*.csv")

    errores = []
    if not csv_sen:  errores.append("senadores_*.csv")
    if not csv_part: errores.append("reporte_partido_senado_*.csv")
    if not csv_prov: errores.append("reporte_provincial_senado_*.csv")
    if errores:
        raise FileNotFoundError(
            f"No se encontraron los siguientes CSVs en {DATA_DIR}/:\n"
            + "\n".join(f"  • {e}" for e in errores)
        )

    print(f"📂 Senadores    : {csv_sen}")
    print(f"📂 Partidos     : {csv_part}")
    print(f"📂 Provincial   : {csv_prov}")

    df_sen  = pd.read_csv(csv_sen,  encoding="utf-8-sig")
    df_part = pd.read_csv(csv_part, encoding="utf-8-sig")
    df_prov = pd.read_csv(csv_prov, encoding="utf-8-sig")

    # Rellenar NaN con 0 / None
    df_sen  = df_sen.fillna({"participation_pct": 0.0, "votos_afirmativos": 0,
                              "votos_negativos": 0, "ausencias": 0,
                              "abstenciones": 0, "votos_total": 0})
    df_part = df_part.fillna({"participation_pct": 0.0, "Mayoría": 0,
                               "Primera Minoría": 0, "votos_afirmativos": 0,
                               "votos_negativos": 0, "abstenciones": 0})
    df_prov = df_prov.fillna({"participation_pct": 0.0, "votos_total": 0,
                               "Mayoría": 0, "Primera Minoría": 0})

    print(f"\n✅ {len(df_sen)} senadores | {len(df_part)} partidos | {len(df_prov)} provincias")

    # ── 2. Construir bloque JS ────────────────────────────────────────────────
    # Extraer fecha del nombre del CSV más reciente
    fecha_csv = os.path.basename(csv_sen).replace("senadores_", "").replace(".csv", "")
    bloque = construir_bloque(df_sen, df_part, df_prov, fecha_csv)

    # ── 3. Reemplazar en el HTML ──────────────────────────────────────────────
    if not os.path.exists(HTML_PATH):
        raise FileNotFoundError(f"No se encontró {HTML_PATH}")

    cambio = actualizar_html(bloque)
    if cambio:
        print(f"\n✅ {HTML_PATH} actualizado con datos del {fecha_csv}")
        # Tamaño del archivo
        size = os.path.getsize(HTML_PATH)
        print(f"   Tamaño: {size:,} bytes")
    else:
        print(f"\nℹ️  {HTML_PATH} sin cambios")


if __name__ == "__main__":
    main()