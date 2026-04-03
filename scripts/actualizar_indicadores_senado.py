"""
scripts/actualizar_indicadores_senado.py
=========================================
Lee el CSV de senadores más reciente y actualiza el array SENADORES
hardcodeado en dashboard/indicadores_senadores.html.

REGLA: no modifica NINGUNA otra parte del HTML.
Solo reemplaza el contenido entre los marcadores:
  // INDICADORES:START
  ...
  // INDICADORES:END

Campos que maneja:
  - nombre, provincia, bloque, genero, inicio_mandato, fin_mandato

Fuentes:
  - nombre, provincia, inicio_mandato, fin_mandato → CSV del scraper
  - bloque   → mapeado desde partido_normalizado via MAPA_BLOQUES
  - genero   → tabla GENERO_CONOCIDO (se preserva para conocidos,
                null para nuevos senadores sin dato)

Uso:
  python scripts/actualizar_indicadores_senado.py
"""

import os
import re
import ast
import glob
import json
import pandas as pd
from datetime import date

# ── Rutas ─────────────────────────────────────────────────────────────────────
DATA_DIR  = "data"
HTML_PATH = "dashboard/indicadores_senadores.html"

MARKER_START = "// INDICADORES:START"
MARKER_END   = "// INDICADORES:END"

HOY = date.today().isoformat()


# ── Mapa partido_normalizado (CSV) → bloque (HTML) ───────────────────────────
# Editá este dict si cambia la composición de bloques en el Senado
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
    # Partidos sin bloque conocido → se deja el nombre tal cual en mayúsculas
}


# ── Tabla de género conocido (apellido normalizado → "M" / "F") ───────────────
# Clave: apellido en minúsculas sin tildes (primer token antes de la coma)
# Extraída del HTML actual — agregar nuevos senadores cuando aparezcan
GENERO_CONOCIDO = {
    "abad": "M",
    "abdala": "M",
    "almeida": "F",
    "alvarez rivero": "F",
    "andrada": "M",
    "arce": "M",
    "arrascaeta": "F",
    "atauche": "M",
    "avila": "F",
    "bahl": "M",
    "bedia": "F",
    "benegas lynch": "M",
    "bensusán": "M",
    "bensusan": "M",
    "bullrich": "F",
    "capitanich": "M",
    "carambia": "M",
    "cervi": "M",
    "corpacci": "F",
    "corroza": "F",
    "coto": "M",
    "cristina": "F",
    "de pedro": "M",
    "di tullio": "F",
    "espínola": "M",
    "espinola": "M",
    "fama": "M",
    "fernández sagasti": "F",
    "fernandez sagasti": "F",
    "fullone": "M",
    "gadano": "F",
    "galaretto": "M",
    "giménez navarro": "F",
    "gimenez navarro": "F",
    "godoy": "M",
    "goerling lara": "M",
    "gonzález": "F",
    "gonzalez": "F",
    "guzmán coraita": "M",
    "guzman coraita": "M",
    "huala": "F",
    "juez": "M",
    "juri": "F",
    "kirchner": "F",
    "kroneberger": "M",
    "lewandowski": "M",
    "linares": "M",
    "lópez": "F",
    "lopez": "F",
    "losada": "F",
    "manzur": "M",
    "marks": "F",
    "márquez": "F",
    "marquez": "F",
    "mayans": "M",
    "mendoza": "F",
    "moises": "F",
    "monte de oca": "F",
    "monteverde": "M",
    "moreno": "F",
    "neder": "M",
    "olivera lucero": "M",
    "orozco": "F",
    "pagotto": "M",
    "paoltroni": "M",
    "recalde": "M",
    "rejal": "M",
    "rojas decut": "F",
    "royon": "F",
    "royón": "F",
    "salino": "M",
    "schneider": "F",
    "soria": "M",
    "suárez": "M",
    "suarez": "M",
    "terenzi": "F",
    "uñac": "M",
    "unac": "M",
    "valenzuela": "F",
    "vigo": "F",
    "vischi": "M",
    "zamora": "M",
}


def _normalizar_texto(txt: str) -> str:
    """Minúsculas y sin tildes para comparación."""
    if not isinstance(txt, str):
        return ""
    reemplazos = str.maketrans("áéíóúÁÉÍÓÚüÜñÑ", "aeiouAEIOUuUnN")
    return txt.strip().lower().translate(reemplazos)


def _apellido_clave(nombre: str) -> str:
    """
    Extrae la clave de apellido para buscar en GENERO_CONOCIDO.
    Formato del CSV: 'Apellido, Nombre' o 'Apellido Compuesto, Nombre'
    """
    partes = nombre.split(",")
    apellido = partes[0].strip()
    return _normalizar_texto(apellido)


def _inferir_genero(nombre: str) -> str:
    """Busca el género en la tabla. Devuelve 'M', 'F' o null (string JS)."""
    clave = _apellido_clave(nombre)
    if clave in GENERO_CONOCIDO:
        return f'"{GENERO_CONOCIDO[clave]}"'
    # Intento por nombre propio (segundo token tras la coma)
    partes = nombre.split(",")
    if len(partes) > 1:
        primer_nombre = partes[1].strip().split()[0] if partes[1].strip() else ""
        pn = _normalizar_texto(primer_nombre)
        terminaciones_f = ("a", "en", "ina", "ela", "ana", "ina", "ela")
        terminaciones_m = ("o", "us", "el", "on", "an", "er")
        if pn.endswith(terminaciones_f) and not pn.endswith(terminaciones_m):
            return '"F"'
        if pn.endswith(terminaciones_m):
            return '"M"'
    print(f"   ⚠️  Género desconocido: {nombre} — usando null")
    return "null"


def _extraer_periodo(periodo_legal_str) -> tuple[int, int]:
    """
    Extrae año de inicio y fin desde la columna periodoLegal del CSV.
    Formato: "{'inicio': '2023-12-10', 'fin': '2029-12-10'}"
    Devuelve (inicio_anio, fin_anio) o (0, 0) si no puede parsear.
    """
    try:
        d = ast.literal_eval(str(periodo_legal_str))
        inicio = int(str(d.get("inicio", "0"))[:4])
        fin    = int(str(d.get("fin",    "0"))[:4])
        return inicio, fin
    except Exception:
        return 0, 0


def _bloque_desde_partido(partido_norm: str) -> str:
    """Convierte partido_normalizado al nombre de bloque del HTML."""
    if partido_norm in MAPA_BLOQUES:
        return MAPA_BLOQUES[partido_norm]
    # Fallback: mayúsculas del partido tal cual
    return str(partido_norm).upper()


def _provincia_a_mayusculas(provincia: str) -> str:
    """Normaliza el nombre de provincia al formato del HTML (mayúsculas)."""
    # El HTML usa mayúsculas y algunos nombres abreviados
    MAP_PROV = {
        "Ciudad Autónoma de Buenos Aires": "CIUDAD AUTÓNOMA DE BUENOS AIRES",
        "Tierra del Fuego, Antártida e Islas del Atlántico Sur": "TIERRA DEL FUEGO",
    }
    if provincia in MAP_PROV:
        return MAP_PROV[provincia]
    return provincia.upper()


def _csv_mas_reciente(patron: str) -> str | None:
    archivos = sorted(glob.glob(os.path.join(DATA_DIR, patron)))
    return archivos[-1] if archivos else None


def construir_array_js(df: pd.DataFrame, fecha: str) -> str:
    """Genera el bloque JS completo con el array SENADORES actualizado."""
    lineas = []
    sin_genero = 0

    # Ordenar alfabéticamente por apellido (igual que el HTML original)
    df = df.copy()
    df["_apellido_sort"] = df["nombre"].str.split(",").str[0].str.strip().str.upper()
    df = df.sort_values("_apellido_sort").reset_index(drop=True)

    for _, row in df.iterrows():
        nombre   = str(row.get("nombre", "")).strip()
        provincia = _provincia_a_mayusculas(str(row.get("provincia", "")).strip())
        partido   = str(row.get("partido_normalizado", row.get("partido", ""))).strip()
        bloque    = _bloque_desde_partido(partido)
        genero_js = _inferir_genero(nombre)
        if genero_js == "null":
            sin_genero += 1

        inicio_anio, fin_anio = _extraer_periodo(row.get("periodoLegal", "{}"))

        lineas.append(
            f'  {{nombre:"{nombre}",provincia:"{provincia}",'
            f'bloque:"{bloque}",genero:{genero_js},'
            f'inicio_mandato:{inicio_anio},fin_mandato:{fin_anio}}}'
        )

    if sin_genero:
        print(f"   ⚠️  {sin_genero} senador(es) sin género conocido (quedan como null)")

    array_js = "var SENADORES = [\n" + ",\n".join(lineas) + "\n];"

    bloque = (
        f"{MARKER_START}\n"
        f"// Datos actualizados automáticamente el {fecha} — no editar a mano\n"
        f"{array_js}\n"
        f"{MARKER_END}"
    )
    return bloque


def actualizar_html(nuevo_bloque: str) -> bool:
    """Reemplaza el contenido entre los marcadores en el HTML."""
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()

    idx_start = contenido.find(MARKER_START)
    idx_end   = contenido.find(MARKER_END)

    if idx_start == -1 or idx_end == -1:
        raise RuntimeError(
            f"No se encontraron los marcadores '{MARKER_START}' / '{MARKER_END}' "
            f"en {HTML_PATH}.\n"
            "Agregalos manualmente alrededor del bloque 'var SENADORES = [...]' "
            "en indicadores_senadores.html."
        )

    bloque_actual = contenido[idx_start: idx_end + len(MARKER_END)]
    if bloque_actual == nuevo_bloque:
        print("ℹ️  El array ya estaba actualizado. Sin cambios.")
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
    print("🔄 Actualizando SENADORES en indicadores_senadores.html")
    print(f"📅 Fecha: {HOY}")
    print("=" * 55)

    csv_sen = _csv_mas_reciente("senadores_*.csv")
    if not csv_sen:
        raise FileNotFoundError(f"No se encontró senadores_*.csv en {DATA_DIR}/")

    print(f"📂 CSV: {csv_sen}")
    df = pd.read_csv(csv_sen, encoding="utf-8-sig")
    print(f"✅ {len(df)} senadores cargados")

    if not os.path.exists(HTML_PATH):
        raise FileNotFoundError(f"No se encontró {HTML_PATH}")

    fecha_csv = os.path.basename(csv_sen).replace("senadores_", "").replace(".csv", "")
    bloque = construir_array_js(df, fecha_csv)

    cambio = actualizar_html(bloque)
    if cambio:
        size = os.path.getsize(HTML_PATH)
        print(f"\n✅ {HTML_PATH} actualizado ({size:,} bytes)")
    else:
        print(f"\nℹ️  {HTML_PATH} sin cambios")


if __name__ == "__main__":
    main()