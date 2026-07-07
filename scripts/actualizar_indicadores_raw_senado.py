"""
scripts/actualizar_indicadores_raw_senado.py
=============================================
Lee el CSV de senadores más reciente y actualiza el array SENADORES_RAW
embebido en dashboard/indicadores.html — la pagina "Indicadores por Senador"
enlazada desde el menu principal del sitio (senado.html, ddjj_senadores.html,
metodologia.html, nomina_detalle_senadores.html).

CONTEXTO / por que existe este script:
  dashboard/indicadores.html tenia su array SENADORES_RAW hardcodeado a mano,
  sin fetch() a la API y sin marcadores de reemplazo -- por eso quedo congelado
  en una fecha vieja mientras el resto del sitio se actualizaba a diario.
  Este script lo integra al mismo patron que ya usan actualizar_fallback_senado.py
  y actualizar_indicadores_senado.py (reemplazo entre marcadores, sin tocar el
  resto del HTML).

REGLA: no modifica NINGUNA otra parte del HTML.
Solo reemplaza el contenido entre los marcadores:
  // SENADORES_RAW:START ... // SENADORES_RAW:END
  <!-- FECHA_DATOS:START --> ... <!-- FECHA_DATOS:END -->

Uso:
  python scripts/actualizar_indicadores_raw_senado.py
"""

import os
import glob
import re
import pandas as pd
from datetime import date

DATA_DIR  = "data"
HTML_PATH = "dashboard/indicadores.html"

MARKER_ARRAY_START = "// SENADORES_RAW:START"
MARKER_ARRAY_END   = "// SENADORES_RAW:END"
MARKER_FECHA_START = "<!-- FECHA_DATOS:START -->"
MARKER_FECHA_END   = "<!-- FECHA_DATOS:END -->"

HOY = date.today().isoformat()


def _csv_mas_reciente(patron: str) -> str | None:
    archivos = sorted(glob.glob(os.path.join(DATA_DIR, patron)))
    return archivos[-1] if archivos else None


def _safe_int(v, default=0) -> int:
    try:
        if pd.isna(v):
            return default
        return int(float(v))
    except Exception:
        return default


def _safe_float(v, default=0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _js_str(v) -> str:
    """Escapa un valor como string JS entre comillas dobles."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '""'
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    # Limpia saltos de linea / espacios pegados de nombres scrapeados (ver di Tullio, Fullone)
    s = re.sub(r"\s+", " ", s).strip()
    return f'"{s}"'


def construir_array_js(df: pd.DataFrame) -> str:
    """Genera el array SENADORES_RAW en el mismo formato que ya usa el HTML."""
    df = df.copy()
    df = df.sort_values("nombre")

    lineas = []
    for _, row in df.iterrows():
        campos = (
            f'id:{_safe_int(row.get("id"))}, '
            f'nombre:{_js_str(row.get("nombre"))}, '
            f'provincia:{_js_str(row.get("provincia"))}, '
            f'partido:{_js_str(row.get("partido_normalizado", row.get("partido")))}, '
            f'rol_provincial:{_js_str(row.get("rol_provincial"))}, '
            f'participation_pct:{_safe_float(row.get("participation_pct"))}, '
            f'votos_afirmativos:{_safe_int(row.get("votos_afirmativos"))}, '
            f'votos_negativos:{_safe_int(row.get("votos_negativos"))}, '
            f'ausencias:{_safe_int(row.get("ausencias"))}, '
            f'abstenciones:{_safe_int(row.get("abstenciones"))}, '
            f'votos_total:{_safe_int(row.get("votos_total"))}, '
            f'foto:{_js_str(row.get("foto"))}, '
            f'email:{_js_str(row.get("email"))}'
        )
        lineas.append(f"  {{ {campos} }}")

    return (
        f"{MARKER_ARRAY_START} -- no editar a mano "
        f"(generado por scripts/actualizar_indicadores_raw_senado.py)\n"
        f"const SENADORES_RAW = [\n"
        + ",\n".join(lineas)
        + "\n];\n"
        + MARKER_ARRAY_END
    )


def actualizar_html(nuevo_bloque_array: str, fecha_csv: str) -> bool:
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()

    idx_start = contenido.find(MARKER_ARRAY_START)
    idx_end   = contenido.find(MARKER_ARRAY_END)
    if idx_start == -1 or idx_end == -1:
        raise RuntimeError(
            f"No se encontraron los marcadores '{MARKER_ARRAY_START}' / "
            f"'{MARKER_ARRAY_END}' en {HTML_PATH}."
        )
    bloque_actual = contenido[idx_start: idx_end + len(MARKER_ARRAY_END)]
    cambio_array = bloque_actual != nuevo_bloque_array
    if cambio_array:
        contenido = (
            contenido[:idx_start]
            + nuevo_bloque_array
            + contenido[idx_end + len(MARKER_ARRAY_END):]
        )

    idx_f1 = contenido.find(MARKER_FECHA_START)
    idx_f2 = contenido.find(MARKER_FECHA_END)
    cambio_fecha = False
    if idx_f1 != -1 and idx_f2 != -1:
        bloque_fecha_actual = contenido[idx_f1: idx_f2 + len(MARKER_FECHA_END)]
        bloque_fecha_nuevo  = f"{MARKER_FECHA_START}{fecha_csv}{MARKER_FECHA_END}"
        cambio_fecha = bloque_fecha_actual != bloque_fecha_nuevo
        if cambio_fecha:
            contenido = (
                contenido[:idx_f1]
                + bloque_fecha_nuevo
                + contenido[idx_f2 + len(MARKER_FECHA_END):]
            )

    if not (cambio_array or cambio_fecha):
        print("ℹ️  indicadores.html ya estaba actualizado. Sin cambios.")
        return False

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(contenido)
    return True


def main():
    print("=" * 55)
    print("Actualizando SENADORES_RAW en dashboard/indicadores.html")
    print(f"Fecha: {HOY}")
    print("=" * 55)

    csv_sen = _csv_mas_reciente("senadores_*.csv")
    if not csv_sen:
        raise FileNotFoundError(f"No se encontro senadores_*.csv en {DATA_DIR}/")

    print(f"CSV: {csv_sen}")
    df = pd.read_csv(csv_sen, encoding="utf-8-sig")
    print(f"{len(df)} senadores cargados")

    if not os.path.exists(HTML_PATH):
        raise FileNotFoundError(f"No se encontro {HTML_PATH}")

    fecha_csv = os.path.basename(csv_sen).replace("senadores_", "").replace(".csv", "")
    bloque = construir_array_js(df)

    cambio = actualizar_html(bloque, fecha_csv)
    if cambio:
        size = os.path.getsize(HTML_PATH)
        print(f"\n{HTML_PATH} actualizado ({size:,} bytes) -- datos al {fecha_csv}")
    else:
        print(f"\n{HTML_PATH} sin cambios")


if __name__ == "__main__":
    main()
