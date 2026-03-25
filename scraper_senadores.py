"""
scraper_senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina
72 senadores: 3 por cada una de las 24 provincias/CABA
  - 2 bancas → partido ganador (mayoría)
  - 1 banca  → primera minoría
Fuentes: ArgentinaDatos API + senado.gob.ar (fallback scraping)

FIXES 2026-03-25:
  - Bug 1: reporte_provincial y reporte_por_partido ahora filtran SOLO
    senadores con mandato vigente (periodoLegal.fin > HOY). Antes tomaban
    los 111 registros históricos, inflando todas las cifras.
  - Bug 2: obtener_nomina() ahora descarta registros cuyo periodoLegal.fin
    ya venció antes de guardar el CSV principal, evitando acumular filas
    de mandatos pasados en senadores_*.csv.
  - Bug 3 (data): Buenos Aires y Río Negro tienen solo 2 activos en la API
    (faltan sus senadores Mayoría del período 2025-2031). El scraper ahora
    loguea una advertencia explícita cuando alguna provincia tiene < 3
    activos, en lugar de silenciarla.
  - Bug 4: Chubut, Mendoza, Santa Fe y Tucumán aparecían con 4 senadores
    porque la API devuelve al senador original Y a su reemplazante cuando
    el titular se fue a otro cargo (gobernador, etc.) y luego volvió.
    deduplicar_provincia() resuelve: si un partido tiene >2 senadores en
    la misma provincia, descarta al(los) de periodoLegal.inicio más antiguo.
  - Bug 5: Buenos Aires y Río Negro tenían solo 2 senadores porque
    ArgentinaDatos no tenía cargados los faltantes del período 2025-2031.
    Se agrega scraping de senado.gob.ar/senadores/listados/listaSenadoRes
    como fuente secundaria de enriquecimiento: después de traer la API,
    se cruza con el sitio oficial y se incorporan los registros que falten.
"""

import ast
import requests
import pandas as pd
import time
import os
from datetime import datetime, date
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)",
    "Accept": "application/json"
}
BASE_API   = "https://api.argentinadatos.com/v1"
HOY        = datetime.today()
HOY_ISO    = date.today().isoformat()   # "2026-03-25"  ← usado para filtrar activos
ANIO_ACTUAL = HOY.year

BLOQUES_MAP = {
    "Unión por la Patria": [
        "alianza unión por la patria", "frente de todos",
        "alianza frente de todos", "frente todos",
        "frente para la victoria", "alianza frente para la victoria",
    ],
    "Unión Cívica Radical": [
        "unión cívica radical", "ucr", "juntos por el cambio",
        "juntos por el cambio tierra del fuego", "juntos por el cambio chubut",
        "frente jujeño cambiemos", "cambiemos fuerza cívica riojana",
        "frente cambiemos", "avanzar y cambiemos por san luis",
        "unión para vivir mejor cambiemos", "cambiemos buenos aires",
        "alianza cambiemos san juan",
    ],
    "La Libertad Avanza": [
        "alianza la libertad avanza", "la libertad avanza",
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
    "Pro / Cambiemos": [
        "pro / cambiemos", "cambiemos buenos aires",
    ],
}


def normalizar_partido(nombre_partido: str) -> str:
    """Normaliza el nombre del partido al bloque legislativo conocido."""
    if not isinstance(nombre_partido, str):
        return "Otros"
    lower = nombre_partido.strip().lower()
    for bloque, aliases in BLOQUES_MAP.items():
        if any(alias in lower for alias in aliases):
            return bloque
    return nombre_partido.strip()


def deduplicar_provincia(df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX Bug 4: cuando la API devuelve >3 senadores por provincia (caso real:
    un titular se fue a otro cargo, fue reemplazado, y luego volvió — la API
    lista a ambos como activos), descarta los registros sobrantes.

    Regla: si un partido tiene >2 senadores en la misma provincia,
    conservar los 2 con periodoLegal.inicio más reciente y descartar el resto.
    """
    def _inicio(periodoLegal_str):
        try:
            return ast.literal_eval(periodoLegal_str).get("inicio", "")
        except Exception:
            return ""

    filas_ok = []
    for provincia, grupo in df.groupby("provincia"):
        if len(grupo) <= 3:
            filas_ok.append(grupo)
            continue
        # Provincia con >3 → revisar partido a partido
        sub_filas = []
        for partido, sub in grupo.groupby("partido_normalizado"):
            if len(sub) > 2:
                sub = sub.copy()
                sub["_inicio_ord"] = sub["periodoLegal"].apply(_inicio)
                descartados = sub.sort_values("_inicio_ord", ascending=False).iloc[2:]
                for _, d in descartados.iterrows():
                    print(f"   ⚠️  Dedup {provincia} / {partido}: "
                          f"descartando '{d['nombre']}' "
                          f"(inicio {d['_inicio_ord']}, reemplazado en su momento)")
                sub = sub.sort_values("_inicio_ord", ascending=False).head(2)
                sub = sub.drop(columns=["_inicio_ord"])
            sub_filas.append(sub)
        filas_ok.append(pd.concat(sub_filas))

    return pd.concat(filas_ok).reset_index(drop=True)


# ── 1. Nómina de Senadores ────────────────────────────────────────────────────
SENADO_URL = "https://www.senado.gob.ar/senadores/listados/listaSenadoRes"
SENADO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MonitorLegislativo/1.0)"}


def _fecha_iso(txt: str) -> str:
    """Convierte DD/MM/YYYY → YYYY-MM-DD. Devuelve '' si no puede."""
    try:
        dd, mm, yy = txt.strip().split("/")
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    except Exception:
        return ""


def scraping_senado_oficial() -> pd.DataFrame:
    """
    Scraping de senado.gob.ar/senadores/listados/listaSenadoRes.
    Devuelve DataFrame con columnas:
      nombre, provincia, partido, inicio, fin, email
    Contiene siempre los 72 senadores vigentes según el sitio oficial.
    """
    try:
        resp = requests.get(SENADO_URL, headers=SENADO_HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Buscar la tabla con más de 10 filas (la de senadores)
        tabla = next(
            (t for t in soup.find_all("table")
             if len(t.find_all("tr")) > 10),
            None
        )
        if not tabla:
            print("⚠️  senado.gob.ar: no se encontró la tabla de senadores")
            return pd.DataFrame()

        registros = []
        for fila in tabla.find_all("tr")[1:]:
            cols = fila.find_all("td")
            if len(cols) < 5:
                continue
            periodo_txt = cols[4].get_text(separator="\n", strip=True)
            partes = [p for p in periodo_txt.split("\n") if p.strip()]
            inicio = _fecha_iso(partes[0]) if len(partes) > 0 else ""
            fin    = _fecha_iso(partes[1]) if len(partes) > 1 else ""
            contacto = cols[5].get_text(separator="\n", strip=True) if len(cols) > 5 else ""
            email = next(
                (l.strip() for l in contacto.split("\n") if "@" in l),
                ""
            )
            registros.append({
                "nombre":   cols[1].get_text(strip=True),
                "provincia": cols[2].get_text(strip=True),
                "partido":  cols[3].get_text(strip=True),
                "inicio":   inicio,
                "fin":      fin,
                "email":    email,
            })

        df = pd.DataFrame(registros)
        # Filtrar solo los vigentes (por si acaso el sitio incluye algún histórico)
        df = df[df["fin"] > HOY_ISO].reset_index(drop=True)
        print(f"✅ senado.gob.ar: {len(df)} senadores vigentes")
        return df

    except Exception as e:
        print(f"⚠️  senado.gob.ar scraping falló: {e}")
        return pd.DataFrame()


def enriquecer_desde_senado(df_api: pd.DataFrame) -> pd.DataFrame:
    """
    FIX Bug 5: cruza df_api con el listado oficial de senado.gob.ar.
    Para cada provincia que tenga < 3 senadores en la API, busca los
    faltantes en el sitio oficial y los incorpora al DataFrame.

    Estrategia de matching: normaliza apellido (primer token antes de la coma)
    para evitar falsos duplicados por diferencias de tilde o inicial.
    """
    provincias_incompletas = (
        df_api.groupby("provincia").size()
        .pipe(lambda s: s[s < 3])
        .index.tolist()
    )
    if not provincias_incompletas:
        return df_api  # Todo completo, nada que hacer

    print(f"\n🔄 Enriqueciendo desde senado.gob.ar "
          f"({len(provincias_incompletas)} provincia(s) incompleta(s))...")
    df_oficial = scraping_senado_oficial()
    if df_oficial.empty:
        print("⚠️  No se pudo obtener datos del sitio oficial. Continuando con lo disponible.")
        return df_api

    # Apellidos ya presentes en la API (normalizados a minúsculas)
    apellidos_api = set(
        df_api["nombre"].str.split(",").str[0].str.strip().str.lower()
    )

    nuevos = []
    for prov in provincias_incompletas:
        candidatos = df_oficial[df_oficial["provincia"] == prov]
        for _, row in candidatos.iterrows():
            apellido = row["nombre"].split(",")[0].strip().lower()
            if apellido not in apellidos_api:
                partido_norm = normalizar_partido(row["partido"])
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
                    "partido_normalizado": partido_norm,
                    "rol_provincial":      None,   # se recalcula después
                })
                apellidos_api.add(apellido)  # evitar doble incorporación
                print(f"   ➕ {row['nombre']} ({prov}) — fuente: senado.gob.ar")

    if nuevos:
        df_nuevos = pd.DataFrame(nuevos)
        df_api = pd.concat([df_api, df_nuevos], ignore_index=True)
        print(f"   Total tras enriquecimiento: {len(df_api)} senadores")
    else:
        print("   ℹ️  No se encontraron registros adicionales en senado.gob.ar")

    return df_api


def asignar_roles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recalcula rol_provincial para todo el DataFrame.
    Regla: dentro de cada provincia, el partido con más bancas
    obtiene 'Mayoría' (máx. 2 senadores); el siguiente obtiene
    'Primera Minoría' (1 senador).
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


def obtener_nomina_fallback():
    """Fallback total: si tanto la API como el enriquecimiento fallan,
    intenta construir la nómina completa desde senado.gob.ar."""
    print("🔄 Usando senado.gob.ar como fuente primaria (fallback total)...")
    df = scraping_senado_oficial()
    if df.empty:
        return pd.DataFrame()
    # Mapear columnas al esquema estándar
    df_std = pd.DataFrame({
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
    return df_std


def obtener_nomina() -> pd.DataFrame:
    """
    Obtiene la nómina completa.
    Flujo:
      1. ArgentinaDatos API  → filtra activos, deduplica
      2. senado.gob.ar       → incorpora los que falten (Bug 5)
      3. asignar_roles()     → recalcula Mayoría / Primera Minoría
    """
    url = f"{BASE_API}/senado/senadores"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
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

        # ── Descartar mandatos ya vencidos ───────────────────────────────────
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
            "rol_provincial":      None,   # se asigna al final con asignar_roles()
        })

    df = pd.DataFrame(registros)
    print(f"✅ API ArgentinaDatos: {len(df)} activos | {descartados} vencidos descartados")

    if df.empty:
        print("⚠️  0 registros activos en la API, usando fallback total...")
        df = obtener_nomina_fallback()
        if not df.empty:
            df = asignar_roles(df)
        return df

    # ── Bug 4: deduplicar provincias con >3 senadores ────────────────────────
    df = deduplicar_provincia(df)

    # ── Bug 5: enriquecer con senado.gob.ar para completar provincias ────────
    df = enriquecer_desde_senado(df)

    # ── Recalcular roles con el conjunto completo ─────────────────────────────
    df = asignar_roles(df)

    # ── Validación final ──────────────────────────────────────────────────────
    total = len(df)
    print(f"\n✅ Nómina final: {total} senadores  (esperado: 72)")
    if total != 72:
        por_prov = df.groupby("provincia").size()
        anom = por_prov[por_prov != 3]
        print(f"⚠️  Faltan {72 - total} senadores. Provincias con ≠ 3:")
        for prov, n in anom.items():
            print(f"   • {prov}: {n}  (faltan {3 - n})")

    return df


# ── 2. Actas de Votación ──────────────────────────────────────────────────────
def obtener_actas(anio: int) -> pd.DataFrame:
    """Obtiene las actas de votación del año indicado."""
    url = f"{BASE_API}/senado/actas/{anio}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        actas = resp.json()
        print(f"✅ Actas {anio}: {len(actas)} votaciones")
        return pd.DataFrame(actas)
    except Exception as e:
        print(f"⚠️  No se pudieron obtener actas {anio}: {e}")
        return pd.DataFrame()


# ── 3. KPIs ───────────────────────────────────────────────────────────────────
def calcular_kpis(df_nomina: pd.DataFrame, df_actas: pd.DataFrame) -> pd.DataFrame:
    """
    Cruza nómina con actas para calcular KPIs de participación.
    Si no hay actas disponibles, devuelve la nómina con columnas KPI en 0.
    """
    if df_actas.empty or "votos" not in df_actas.columns:
        df_nomina = df_nomina.copy()
        df_nomina["votos_total"]       = 0
        df_nomina["votos_afirmativos"] = 0
        df_nomina["votos_negativos"]   = 0
        df_nomina["abstenciones"]      = 0
        df_nomina["ausencias"]         = 0
        df_nomina["participation_pct"] = 0.0
        return df_nomina

    filas = []
    for _, acta in df_actas.iterrows():
        for voto in acta.get("votos", []):
            filas.append({
                "nombre": voto.get("nombre", ""),
                "voto":   voto.get("voto", ""),
            })
    df_votos = pd.DataFrame(filas)

    if df_votos.empty:
        df_nomina = df_nomina.copy()
        df_nomina["votos_total"]       = 0
        df_nomina["participation_pct"] = 0.0
        return df_nomina

    resumen = (
        df_votos.groupby("nombre")["voto"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    # La API devuelve votos en minúsculas: "si", "no", "abstencion", "ausente"
    for col in ["si", "no", "abstencion", "ausente"]:
        if col not in resumen.columns:
            resumen[col] = 0

    resumen = resumen.rename(columns={
        "si":         "votos_afirmativos",
        "no":         "votos_negativos",
        "abstencion": "abstenciones",
        "ausente":    "ausencias",
    })
    resumen["votos_total"] = (
        resumen["votos_afirmativos"]
        + resumen["votos_negativos"]
        + resumen["abstenciones"]
        + resumen["ausencias"]
    )
    total_sesiones = df_actas.shape[0]
    resumen["participation_pct"] = (
        (resumen["votos_afirmativos"] + resumen["votos_negativos"] + resumen["abstenciones"])
        / total_sesiones * 100
    ).round(2)

    df_final = df_nomina.merge(resumen, on="nombre", how="left")
    for col in ["votos_total", "votos_afirmativos", "votos_negativos",
                "abstenciones", "ausencias"]:
        df_final[col] = df_final[col].fillna(0).astype(int)
    df_final["participation_pct"] = df_final["participation_pct"].fillna(0.0)

    return df_final


# ── 4. Reporte Provincial ─────────────────────────────────────────────────────
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX: El DataFrame ya llega filtrado (solo activos desde obtener_nomina).
    Agrupa por provincia y contabiliza senadores y bloques.
    Emite advertencia si alguna provincia tiene < 3 senadores activos.
    """
    rp = (
        df.groupby("provincia")
        .agg(
            senadores=("nombre", "count"),
            partidos=("partido_normalizado",
                      lambda x: " / ".join(sorted(x.unique())))
        )
        .reset_index()
        .sort_values("provincia")
        .reset_index(drop=True)
    )

    # ── FIX Bug 3: advertencia de provincias incompletas ───────────────────
    incompletas = rp[rp["senadores"] < 3]
    if not incompletas.empty:
        print("\n⚠️  ADVERTENCIA — Provincias con < 3 senadores activos en la fuente:")
        for _, row in incompletas.iterrows():
            print(f"   • {row['provincia']}: {row['senadores']} senador(es) "
                  "— verificar en la API si el dato ya fue cargado")
        print()
    # ────────────────────────────────────────────────────────────────────────

    return rp


# ── 5. Reporte por Partido ────────────────────────────────────────────────────
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    """
    FIX: El DataFrame ya llega filtrado (solo activos).
    El total de bancas debe sumar 72 (o el número real si la API
    tiene datos incompletos).
    """
    rpartido = (
        df.groupby("partido_normalizado")
        .agg(
            bancas=("nombre", "count"),
            Mayoría=("rol_provincial", lambda x: (x == "Mayoría").sum()),
            Primera_Minoria=("rol_provincial",
                             lambda x: (x == "Primera Minoría").sum()),
        )
        .reset_index()
        .rename(columns={
            "partido_normalizado": "partido",
            "Primera_Minoria": "Primera Minoría",
        })
        .sort_values("bancas", ascending=False)
        .reset_index(drop=True)
    )

    total = rpartido["bancas"].sum()
    if total != 72:
        print(f"⚠️  Reporte partido: {total} bancas en total "
              f"(esperado 72 — faltan {72 - total} en la fuente)")

    return rpartido


# ── 6. Guardar Resultados ─────────────────────────────────────────────────────
def guardar_resultados(df_final: pd.DataFrame,
                       df_provincial: pd.DataFrame,
                       df_partido: pd.DataFrame) -> None:
    """Guarda los tres CSVs en la carpeta data/."""
    os.makedirs("data", exist_ok=True)
    fecha = HOY.strftime("%Y-%m-%d")

    paths = {
        "senadores":          f"data/senadores_{fecha}.csv",
        "reporte_provincial": f"data/reporte_provincial_{fecha}.csv",
        "reporte_partido":    f"data/reporte_partido_{fecha}.csv",
    }

    df_final.to_csv(paths["senadores"],           index=False)
    df_provincial.to_csv(paths["reporte_provincial"], index=False)
    df_partido.to_csv(paths["reporte_partido"],    index=False)

    for nombre, path in paths.items():
        size = os.path.getsize(path)
        print(f"💾 {nombre:20s} → {path}  ({size:,} bytes)")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🏛️  Monitor Legislativo — Senado Nacional")
    print(f"📅 Fecha: {HOY_ISO}")
    print("=" * 60)

    # 1. Nómina (filtrada a activos dentro de obtener_nomina)
    df_nomina = obtener_nomina()
    if df_nomina.empty:
        print("❌ No se pudo obtener la nómina. Abortando.")
        exit(1)

    # 2. Actas
    time.sleep(0.5)
    df_actas = obtener_actas(ANIO_ACTUAL)
    if df_actas.empty:
        time.sleep(1)
        df_actas = obtener_actas(ANIO_ACTUAL - 1)

    # 3. KPIs
    df_final = calcular_kpis(df_nomina, df_actas)

    # 4. Reportes — sobre datos ya filtrados ✅
    df_provincial = reporte_provincial(df_final)
    df_partido    = reporte_por_partido(df_final)

    # 5. Guardar
    guardar_resultados(df_final, df_provincial, df_partido)

    # ── Resumen consola ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO")
    print("=" * 60)
    print(f"\n🗺️  Provincias representadas : {df_final['provincia'].nunique()}")
    print(f"👥 Senadores activos         : {len(df_final)}  (esperado: 72)")

    if "partido_normalizado" in df_final.columns:
        print(f"\n🏛️  Bancas por Partido:")
        print(df_final["partido_normalizado"].value_counts().to_string())

    if "rol_provincial" in df_final.columns:
        print(f"\n⚖️  Mayorías vs Minorías:")
        print(df_final["rol_provincial"].value_counts().to_string())

    if not df_provincial.empty:
        print(f"\n📊 Reporte Provincial:")
        print(df_provincial.to_string(index=False))

    if not df_partido.empty:
        print(f"\n🗳️  Reporte por Partido:")
        print(df_partido.to_string(index=False))
        print(f"\n   Total bancas: {df_partido['bancas'].sum()}")
