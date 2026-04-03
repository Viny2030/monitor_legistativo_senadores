"""
scripts/actualizar_bloques_nomina_senado.py
============================================
Actualiza el array SENADORES hardcodeado en:
  - dashboard/indicadores_bloques_senadores.html
  - dashboard/nomina_detalle_senadores.html

Estos archivos usan solo: nombre, provincia, bloque
(sin genero ni mandato — se calculan en JS en tiempo real)

REGLA: no modifica NINGUNA otra parte del HTML.
Reemplaza solo entre marcadores:
  // BLOQUES:START  /  // BLOQUES:END
  // NOMINA:START   /  // NOMINA:END

Uso:
  python scripts/actualizar_bloques_nomina_senado.py
"""

import os
import glob
import json
import pandas as pd
from datetime import date

DATA_DIR = "data"
HOY = date.today().isoformat()

# ── Archivos y marcadores ──────────────────────────────────────────────────────
TARGETS = [
    {
        "path":    "dashboard/indicadores_bloques_senadores.html",
        "start":   "// BLOQUES:START",
        "end":     "// BLOQUES:END",
        "label":   "indicadores_bloques_senadores.html",
    },
    {
        "path":    "dashboard/nomina_detalle_senadores.html",
        "start":   "// NOMINA:START",
        "end":     "// NOMINA:END",
        "label":   "nomina_detalle_senadores.html",
    },
]

# ── Mapa partido_normalizado → bloque HTML ────────────────────────────────────
MAPA_BLOQUES = {
    "La Libertad Avanza":                                    "LA LIBERTAD AVANZA",
    "Unión por la Patria":                                   "JUSTICIALISTA",
    "Unión Cívica Radical":                                  "UCR - UNIÓN CÍVICA RADICAL",
    "Pro / Cambiemos":                                       "FRENTE PRO",
    "Fuerza Patria":                                         "JUSTICIALISTA",
    "Hacemos por Córdoba":                                   "PROVINCIAS UNIDAS",
    "Eco + Vamos Corrientes":                                "PROVINCIAS UNIDAS",
    "Alianza por Santa Cruz":                                "MOVERE POR SANTA CRUZ",
    "Partido Renovador Federal":                             "JUSTICIA SOCIAL FEDERAL",
    "Frente Renovador de la Concordia-Innovación Federal":   "FRENTE RENOVADOR DE LA CONCORDIA SOCIAL",
    "Frente Cívico por Santiago":                            "FRENTE CÍVICO POR SANTIAGO",
    "Primero Los Salteños":                                  "PRIMERO LOS SALTEÑOS",
    "la Neuquinidad":                                        "LA NEUQUINIDAD",
    "Frente Cambia Mendoza":                                 "UCR - UNIÓN CÍVICA RADICAL",
    "Fuerza Entre Ríos":                                     "JUSTICIALISTA",
}

MAP_PROV = {
    "Ciudad Autónoma de Buenos Aires": "CIUDAD AUTÓNOMA DE BUENOS AIRES",
    "Tierra del Fuego, Antártida e Islas del Atlántico Sur": "TIERRA DEL FUEGO",
}


def _csv_mas_reciente(patron):
    archivos = sorted(glob.glob(os.path.join(DATA_DIR, patron)))
    return archivos[-1] if archivos else None


def _bloque(partido):
    return MAPA_BLOQUES.get(str(partido).strip(), str(partido).strip().upper())


def _provincia(prov):
    return MAP_PROV.get(str(prov).strip(), str(prov).strip().upper())


def _format(v):
    if v is None:
        return "null"
    return json.dumps(str(v), ensure_ascii=False)


def construir_array(df, fecha):
    """Genera: const SENADORES=[{nombre,provincia,bloque},...];"""
    df = df.copy()
    df["_sort"] = df["nombre"].str.split(",").str[0].str.strip().str.upper()
    df = df.sort_values("_sort").reset_index(drop=True)

    lineas = []
    for _, row in df.iterrows():
        nombre   = _format(str(row.get("nombre", "")).strip())
        provincia = _format(_provincia(row.get("provincia", "")))
        bloque   = _format(_bloque(row.get("partido_normalizado", row.get("partido", ""))))
        lineas.append(f"  {{nombre:{nombre},provincia:{provincia},bloque:{bloque}}}")

    array_js = "const SENADORES=[\n" + ",\n".join(lineas) + "\n];"
    return array_js


def construir_bloque(array_js, marker_start, marker_end, fecha):
    return (
        f"{marker_start}\n"
        f"// Actualizado automáticamente el {fecha} — no editar a mano\n"
        f"{array_js}\n"
        f"{marker_end}"
    )


def actualizar_html(path, nuevo_bloque, marker_start, marker_end):
    with open(path, "r", encoding="utf-8") as f:
        contenido = f.read()

    idx_start = contenido.find(marker_start)
    idx_end   = contenido.find(marker_end)

    if idx_start == -1 or idx_end == -1:
        raise RuntimeError(
            f"No se encontraron marcadores '{marker_start}' / '{marker_end}' en {path}"
        )

    bloque_actual = contenido[idx_start: idx_end + len(marker_end)]
    if bloque_actual == nuevo_bloque:
        print(f"   ℹ️  Sin cambios")
        return False

    nuevo_contenido = (
        contenido[:idx_start]
        + nuevo_bloque
        + contenido[idx_end + len(marker_end):]
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(nuevo_contenido)
    return True


def main():
    print("=" * 55)
    print("🔄 Actualizando bloques y nómina detallada")
    print(f"📅 Fecha: {HOY}")
    print("=" * 55)

    csv_sen = _csv_mas_reciente("senadores_*.csv")
    if not csv_sen:
        raise FileNotFoundError(f"No se encontró senadores_*.csv en {DATA_DIR}/")

    print(f"📂 CSV: {csv_sen}")
    df = pd.read_csv(csv_sen, encoding="utf-8-sig")
    print(f"✅ {len(df)} senadores cargados")

    fecha_csv = os.path.basename(csv_sen).replace("senadores_", "").replace(".csv", "")
    array_js = construir_array(df, fecha_csv)

    for t in TARGETS:
        path = t["path"]
        print(f"\n📄 {t['label']}")
        if not os.path.exists(path):
            print(f"   ⚠️  No encontrado: {path} — saltando")
            continue
        bloque = construir_bloque(array_js, t["start"], t["end"], fecha_csv)
        cambio = actualizar_html(path, bloque, t["start"], t["end"])
        if cambio:
            size = os.path.getsize(path)
            print(f"   ✅ Actualizado ({size:,} bytes)")

    print("\n✅ Listo")


if __name__ == "__main__":
    main()