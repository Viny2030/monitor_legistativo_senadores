"""
scrapers/senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina

72 senadores: 3 por cada una de las 24 provincias/CABA
  - 2 bancas → partido ganador (mayoría)
  - 1 banca  → primera minoría
  - Mandatos de 6 años, renovación por tercios cada 2 años

Fuentes (en orden de prioridad):
  1. ArgentinaDatos API  → https://api.argentinadatos.com/v1/senado/senadores
  2. senado.gob.ar       → enriquecimiento/completado de faltantes
  3. Fallback total      → senado.gob.ar como fuente primaria

Fixes aplicados vs versión original:
  - Bug 1/2: filtra SOLO mandatos vigentes (periodoLegal.fin > HOY)
  - Bug 3:   BLOQUES_MAP expandido con todos los partidos 2021-2031
  - Bug 4:   deduplicar_provincia() elimina dobles cuando un senador
             se fue a otro cargo, fue reemplazado y luego volvió
  - Bug 5:   enriquecer_desde_senado() incorpora faltantes de la API
             (ej: di Tullio/BA y Fullone/RN del período 2025-2031)
  - Bug 6:   endpoints corregidos (/senado/... en lugar de /congreso/...)
  - Bug 7:   votos en actas vienen en minúsculas ("si"/"no"/"abstencion")
"""

import ast
import requests
import pandas as pd
import os
import time
from datetime import datetime, date
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
HEADERS_API = {
    "User-Agent": "MonitorLegislativo/1.0 (github.com/Viny2030)",
    "Accept":     "application/json",
}
HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (compatible; MonitorLegislativo/1.0)",
}

BASE_API    = "https://api.argentinadatos.com/v1"
SENADO_URL  = "https://www.senado.gob.ar/senadores/listados/listaSenadoRes"
HOY         = datetime.today()
HOY_ISO     = date.today().isoformat()
ANIO_ACTUAL = HOY.year

# ── Mapa de normalización de partidos ─────────────────────────────────────────
BLOQUES_MAP = {
    "Unión por la Patria": [
        "alianza unión por la patria", "frente de todos", "alianza frente de todos",
        "alianza frente para la victoria", "frente todos", "frente para la victoria",
        "peronista", "justicialista", "frente fuerza patria peronista",
    ],
    "La Libertad Avanza": [
        "alianza la libertad avanza", "la libertad avanza", "libertad avanza",
    ],
    "Unión Cívica Radical": [
        "unión cívica radical", "ucr", "juntos por el cambio",
        "juntos por el cambio tierra del fuego", "juntos por el cambio chubut",
        "frente jujeño cambiemos", "avanzar y cambiemos por san luis",
        "unión para vivir mejor cambiemos", "cambiemos buenos aires",
        "alianza cambiemos san juan",
    ],
    "Pro / Cambiemos": [
        "pro / cambiemos", "cambiemos buenos aires", "pro",
    ],
    "Fuerza Patria": [
        "fuerza patria",
    ],
    "Frente Cívico por Santiago": [
        "frente cívico por santiago",
    ],
    "Hacemos por Córdoba": [
        "hacemos por córdoba",
    ],
    "Eco + Vamos Corrientes": [
        "eco + vamos corrientes",
    ],
    "Frente Cambia Mendoza": [
        "frente cambia mendoza",
    ],
    "Alianza por Santa Cruz": [
        "alianza por santa cruz",
    ],
    "Partido Renovador Federal": [
        "partido renovador federal",
    ],
    "Frente Renovador de la Concordia-Innovación Federal": [
        "frente renovador de la concordia-innovación federal",
        "frente renovador de la concordia innovación federal",
    ],
    "Frente Renovador de la Concordia": [
        "frente renovador de la concordia",
    ],
    "Fuerza Entre Ríos": [
        "fuerza entre ríos",
    ],
    "Primero Los Salteños": [
        "primero los salteños",
    ],
    "la Neuquinidad": [
        "la neuquinidad",
    ],
    "Juntos Somos Río Negro": [
        "juntos somos río negro",
    ],
    "Frente Amplio Formoseño Cambiemos": [
        "frente amplio formoseño cambiemos",
    ],
    "Frente Cambiemos": [
        "frente cambiemos",
    ],
    "Cambiemos Fuerza Cívica Riojana": [
        "cambiemos fuerza cívica riojana",
    ],
}


# ── Utilidades ────────────────────────────────────────────────────────────────
def normalizar_partido(nombre: str) -> str:
    if not isinstance(nombre, str):
        return "Otros"
    lower = nombre.strip().lower()
    for bloque, aliases in BLOQUES_MAP.items():
        if any(alias in lower for alias in aliases):
            return bloque
    return nombre.strip()


def _fecha_iso(txt: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD."""
    try:
        dd, mm, yy = txt.strip().split("/")
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    except Exception:
        return ""


def deduplicar_provincia(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cuando la API devuelve >3 senadores por provincia (un titular que se fue
    a otro cargo, fue reemplazado y luego volvió), descarta los sobrantes.
    Regla: si un partido tiene >2 senadores en la misma provincia,
    conservar los 2 con periodoLegal.inicio más reciente.
    """
    def _inicio(s):
        try:
            return ast.literal_eval(s).get("inicio", "")
        except Exception:
            return ""

    filas_ok = []
    for provincia, grupo in df.groupby("provincia"):
        if len(grupo) <= 3:
            filas_ok.append(grupo)
            continue
        sub_filas = []
        for partido, sub in grupo.groupby("partido_normalizado"):
            if len(sub) > 2:
                sub = sub.copy()
                sub["_ini"] = sub["periodoLegal"].apply(_inicio)
                descartados = sub.sort_values("_ini", ascending=False).iloc[2:]
                for _, d in descartados.iterrows():
                    print(f"   ⚠️  Dedup {provincia}/{partido}: "
                          f"descartando '{d['nombre']}' (reemplazado, fin volvió)")
                sub = sub.sort_values("_ini", ascending=False).head(2).drop(columns=["_ini"])
            sub_filas.append(sub)
        filas_ok.append(pd.concat(sub_filas))

    return pd.concat(filas_ok).reset_index(drop=True)


def asignar_roles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recalcula rol_provincial para todo el DataFrame.
    Dentro de cada provincia: partido mayoritario → 'Mayoría' (máx. 2),
    partido siguiente → 'Primera Minoría' (1).
    """
    df = df.copy()
    df["rol_provincial"] = None
    for provincia, grupo in df.groupby("provincia"):
        conteo  = grupo["partido_normalizado"].value_counts()
        mayoria = conteo.index[0] if len(conteo) >= 1 else None
        minoria = conteo.index[1] if len(conteo) >= 2 else None
        asignados = {}
        for idx, row in grupo.iterrows():
            p = row["partido_normalizado"]
            asignados[p] = asignados.get(p, 0) + 1
            if p == mayoria and asignados[p] <= 2:
                df.at[idx, "rol_provincial"] = "Mayoría"
            elif p == minoria:
                df.at[idx, "rol_provincial"] = "Primera Minoría"
            else:
                df.at[idx, "rol_provincial"] = "Mayoría"
    return df


# ── Scraping senado.gob.ar ────────────────────────────────────────────────────
def scraping_senado_oficial() -> pd.DataFrame:
    """
    Scraping de senado.gob.ar/senadores/listados/listaSenadoRes.
    Devuelve los 72 senadores vigentes con: nombre, provincia, partido,
    inicio, fin, email.
    """
    try:
        resp = requests.get(SENADO_URL, headers=HEADERS_WEB, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        tabla = next(
            (t for t in soup.find_all("table") if len(t.find_all("tr")) > 10),
            None
        )
        if not tabla:
            print("⚠️  senado.gob.ar: tabla no encontrada")
            return pd.DataFrame()

        registros = []
        for fila in tabla.find_all("tr")[1:]:
            cols = fila.find_all("td")
            if len(cols) < 5:
                continue
            periodo = cols[4].get_text(separator="\n", strip=True).split("\n")
            periodo = [p for p in periodo if p.strip()]
            inicio = _fecha_iso(periodo[0]) if len(periodo) > 0 else ""
            fin    = _fecha_iso(periodo[1]) if len(periodo) > 1 else ""
            contacto = cols[5].get_text(separator="\n", strip=True) if len(cols) > 5 else ""
            email = next((l.strip() for l in contacto.split("\n") if "@" in l), "")
            registros.append({
                "nombre":   cols[1].get_text(strip=True),
                "provincia": cols[2].get_text(strip=True),
                "partido":  cols[3].get_text(strip=True),
                "inicio":   inicio,
                "fin":      fin,
                "email":    email,
            })

        df = pd.DataFrame(registros)
        df = df[df["fin"] > HOY_ISO].reset_index(drop=True)
        print(f"✅ senado.gob.ar: {len(df)} senadores vigentes")
        return df

    except Exception as e:
        print(f"⚠️  senado.gob.ar scraping falló: {e}")
        return pd.DataFrame()


def enriquecer_desde_senado(df_api: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada provincia con < 3 senadores en la API, busca los faltantes
    en senado.gob.ar y los incorpora. Marca la fuente en 'observaciones'.
    """
    provincias_incompletas = (
        df_api.groupby("provincia").size()
        .pipe(lambda s: s[s < 3]).index.tolist()
    )
    if not provincias_incompletas:
        return df_api

    print(f"\n🔄 Enriqueciendo desde senado.gob.ar "
          f"({len(provincias_incompletas)} provincia(s) incompleta(s))...")
    df_oficial = scraping_senado_oficial()
    if df_oficial.empty:
        print("⚠️  No se pudo obtener datos del sitio oficial.")
        return df_api

    apellidos_api = set(
        df_api["nombre"].str.split(",").str[0].str.strip().str.lower()
    )

    nuevos = []
    for prov in provincias_incompletas:
        candidatos = df_oficial[df_oficial["provincia"] == prov]
        for _, row in candidatos.iterrows():
            apellido = row["nombre"].split(",")[0].strip().lower()
            if apellido not in apellidos_api:
                nuevos.append({
                    "id":                  None,
                    "nombre":              row["nombre"],
                    "provincia":           row["provincia"],
                    "partido":             row["partido"],
                    "periodoLegal":        str({"inicio": row["inicio"], "fin": row["fin"]}),
                    "periodoReal":         str({}),
                    "reemplazo":           None,
                    "observaciones":       "Incorporado desde senado.gob.ar (ausente en API)",
                    "foto":                None,
                    "email":               row["email"],
                    "telefono":            None,
                    "redes":               None,
                    "partido_normalizado": normalizar_partido(row["partido"]),
                    "rol_provincial":      None,
                })
                apellidos_api.add(apellido)
                print(f"   ➕ {row['nombre']} ({prov})")

    if nuevos:
        df_api = pd.concat([df_api, pd.DataFrame(nuevos)], ignore_index=True)
        print(f"   Total tras enriquecimiento: {len(df_api)} senadores")
    else:
        print("   ℹ️  No se encontraron registros adicionales en senado.gob.ar")

    return df_api


def obtener_nomina_fallback() -> pd.DataFrame:
    """Fallback total: construye la nómina completa desde senado.gob.ar."""
    print("🔄 Fallback total: usando senado.gob.ar como fuente primaria...")
    df = scraping_senado_oficial()
    if df.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "id":                  None,
        "nombre":              df["nombre"],
        "provincia":           df["provincia"],
        "partido":             df["partido"],
        "periodoLegal":        df.apply(
            lambda r: str({"inicio": r["inicio"], "fin": r["fin"]}), axis=1),
        "periodoReal":         str({}),
        "reemplazo":           None,
        "observaciones":       "Fuente: senado.gob.ar (fallback total)",
        "foto":                None,
        "email":               df["email"],
        "telefono":            None,
        "redes":               None,
        "partido_normalizado": df["partido"].apply(normalizar_partido),
        "rol_provincial":      None,
    })


# ── Nómina principal ──────────────────────────────────────────────────────────
def obtener_nomina(guardar_csv: bool = True,
                   ruta_salida: str = "data/nomina_senadores.csv") -> pd.DataFrame:
    """
    Punto de entrada principal. Flujo:
      1. ArgentinaDatos API  → filtra activos, deduplica
      2. senado.gob.ar       → incorpora los que falten
      3. asignar_roles()     → recalcula Mayoría / Primera Minoría
    """
    print("\n" + "=" * 55)
    print("  EXTRACTOR DE NÓMINA DE SENADORES")
    print("=" * 55)

    # ── 1. API ArgentinaDatos ─────────────────────────────────────────────────
    url = f"{BASE_API}/senado/senadores"
    try:
        resp = requests.get(url, headers=HEADERS_API, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"⚠️  API ArgentinaDatos falló ({e}), usando fallback total...")
        df = obtener_nomina_fallback()
        if not df.empty:
            df = asignar_roles(df)
        return df

    registros = []
    descartados = 0
    for s in data:
        periodo_legal = s.get("periodoLegal", {})
        fin_legal     = periodo_legal.get("fin", "")
        if not fin_legal or fin_legal <= HOY_ISO:
            descartados += 1
            continue
        periodo_real = s.get("periodoReal", {})
        registros.append({
            "id":                  s.get("id"),
            "nombre":              s.get("nombre"),
            "provincia":           s.get("provincia"),
            "partido":             s.get("partido"),
            "periodoLegal":        str(periodo_legal),
            "periodoReal":         str(periodo_real),
            "reemplazo":           s.get("reemplazo"),
            "observaciones":       s.get("observaciones"),
            "foto":                s.get("foto"),
            "email":               s.get("email"),
            "telefono":            s.get("telefono"),
            "redes":               str(s.get("redesSociales")) if s.get("redesSociales") else None,
            "partido_normalizado": normalizar_partido(s.get("partido", "")),
            "rol_provincial":      None,
        })

    df = pd.DataFrame(registros)
    print(f"✅ API: {len(df)} activos | {descartados} vencidos descartados")

    if df.empty:
        print("⚠️  0 activos en la API, usando fallback total...")
        df = obtener_nomina_fallback()
        if not df.empty:
            df = asignar_roles(df)
        return df

    # ── 2. Deduplicar provincias con >3 senadores ─────────────────────────────
    df = deduplicar_provincia(df)

    # ── 3. Completar desde senado.gob.ar ─────────────────────────────────────
    df = enriquecer_desde_senado(df)

    # ── 4. Asignar roles con el conjunto completo ─────────────────────────────
    df = asignar_roles(df)

    # ── 5. Validación final ───────────────────────────────────────────────────
    total = len(df)
    print(f"\n✅ Nómina final: {total} senadores  (esperado: 72)")
    if total != 72:
        por_prov = df.groupby("provincia").size()
        for prov, n in por_prov[por_prov != 3].items():
            print(f"   ⚠️  {prov}: {n} senadores (faltan {3 - n} — dato ausente en fuentes)")

    print(f"\n📌 Distribución por Bloque:")
    print(df["partido_normalizado"].value_counts().to_string())

    # ── 6. Guardar ────────────────────────────────────────────────────────────
    if guardar_csv:
        os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
        df.to_csv(ruta_salida, index=False, encoding="utf-8-sig")
        print(f"\n💾 Guardado en: {ruta_salida} ({len(df)} filas)")

    return df


# ── Actas de votación ─────────────────────────────────────────────────────────
def obtener_actas(anio: int = None) -> pd.DataFrame:
    """
    Obtiene las actas de votación del Senado para el año indicado.
    Endpoint: /v1/senado/actas/{anio}
    Los votos vienen en minúsculas: "si", "no", "abstencion", "ausente".
    """
    anio = anio or ANIO_ACTUAL
    url  = f"{BASE_API}/senado/actas/{anio}"
    try:
        resp = requests.get(url, headers=HEADERS_API, timeout=30)
        resp.raise_for_status()
        actas = resp.json()
        print(f"✅ Actas {anio}: {len(actas)} votaciones")
        return pd.DataFrame(actas)
    except Exception as e:
        print(f"⚠️  Actas {anio} no disponibles: {e}")
        return pd.DataFrame()


if __name__ == "__main__":
    df = obtener_nomina()
