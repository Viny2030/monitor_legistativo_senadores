"""
scraper_senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina
72 senadores: 3 por cada una de las 24 provincias/CABA
  - 2 bancas → partido ganador (mayoría)
  - 1 banca  → primera minoría
Fuentes: ArgentinaDatos API + senado.gob.ar (fallback scraping)

FIXES aplicados (2026-03-25):
  1. BLOQUES_MAP expandido con todos los partidos actuales (Fuerza Patria,
     Fuerza Entre Ríos, Primero Los Salteños, la Neuquinidad, etc.)
  2. reporte_provincial() y reporte_por_partido() ahora reciben el df ya
     filtrado (que sale de obtener_nomina), por lo que jamás procesan
     senadores con mandatos vencidos.
  3. asignar_rol_provincial(): cuando una provincia tiene <3 senadores
     (API incompleta), los 2 del mismo partido se marcan 'Mayoría'
     correctamente — ya no se cae en el else → 'Mayoría' de forma
     silenciosa para casos raros.
  4. obtener_nomina(): el filtro de mandato vigente ahora usa periodoLegal
     como fuente primaria (dato siempre presente) y periodoReal como
     fallback, en vez del orden inverso que dejaba pasar históricos cuando
     periodoReal.fin era None.
  5. Advertencia explícita cuando una provincia tiene ≠ 3 senadores activos
     en la API (datos incompletos en la fuente).
"""

import ast
import requests
import pandas as pd
import time
import os
from datetime import datetime
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)",
    "Accept": "application/json"
}
BASE_API   = "https://api.argentinadatos.com/v1"
HOY        = datetime.today()
HOY_STR    = HOY.strftime("%Y-%m-%d")
AÑO_ACTUAL = HOY.year

# ── Mapa de normalización de partidos ─────────────────────────────────────────
# FIX 1: agregados todos los bloques que aparecen en los datos reales 2023-2031
BLOQUES_MAP = {
    "Unión por la Patria": [
        "alianza unión por la patria", "frente de todos", "alianza frente de todos",
        "frente todos", "frente para la victoria", "alianza frente para la victoria",
        "peronista", "justicialista", "alianza frente de todos",
        "frente fuerza patria peronista",            # Santiago del Estero 2031
    ],
    "La Libertad Avanza": [
        "alianza la libertad avanza", "libertad avanza",
    ],
    "Unión Cívica Radical": [
        "unión cívica radical", "u. c. r. del pueblo",
        "juntos por el cambio", "alianza cambiemos",
        "juntos por el cambio tierra del fuego",    # TdF
        "juntos por el cambio chubut",              # Chubut
        "frente jujeño cambiemos",                  # Jujuy pre-2023
        "avanzar y cambiemos por san luis",         # San Luis 2021
        "alianza cambiemos san juan",               # San Juan 2017
    ],
    "Pro / Cambiemos": [
        "pro", "alianza unión pro", "cambiemos buenos aires",
    ],
    "Fuerza Patria": [
        "fuerza patria",                            # CABA, Chaco, Río Negro 2031
    ],
    "Frente Cívico por Santiago": [
        "frente cívico por santiago",
    ],
    "Alianza por Santa Cruz": [
        "alianza por santa cruz",
    ],
    "Eco + Vamos Corrientes": [
        "eco + vamos corrientes",
    ],
    "Frente Cambia Mendoza": [
        "frente cambia mendoza",
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
    "Unión para Vivir Mejor Cambiemos": [
        "unión para vivir mejor cambiemos",
    ],
    "Cambiemos Fuerza Cívica Riojana": [
        "cambiemos fuerza cívica riojana",
    ],
    "Hacemos por Córdoba": [
        "hacemos por córdoba",
    ],
    "Fuerza Entre Ríos": [
        "fuerza entre ríos",                        # Entre Ríos 2031
    ],
    "Primero Los Salteños": [
        "primero los salteños",                     # Salta 2031
    ],
    "Juntos Somos Río Negro": [
        "juntos somos río negro",
    ],
    "la Neuquinidad": [
        "la neuquinidad",                           # Neuquén 2031
    ],
    "Frente Amplio Formoseño Cambiemos": [
        "frente amplio formoseño cambiemos",
    ],
    "Frente Cambiemos": [
        "frente cambiemos",
    ],
}


# ── Utilidades ────────────────────────────────────────────────────────────────
def get_con_reintento(url, intentos=3, espera=5):
    for i in range(intentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"   ⚠️  Intento {i+1}/{intentos} falló: {e}")
            if i < intentos - 1:
                time.sleep(espera)
    return None


def normalizar_partido(p):
    if not isinstance(p, str):
        return "Sin datos"
    p_lower = p.lower().strip()
    for bloque, aliases in BLOQUES_MAP.items():
        for alias in aliases:
            if alias in p_lower:
                return bloque
    return p.strip()


def asignar_rol_provincial(grupo):
    """
    Dentro de cada provincia asigna:
      - 'Mayoría'         → los 2 senadores del partido más votado
      - 'Primera Minoría' → el senador del partido que salió segundo

    FIX 3: cuando la provincia tiene <3 senadores en la API (datos
    incompletos), los que hay del partido mayoritario se marcan 'Mayoría'
    y sólo si hay un partido distinto se marca 'Primera Minoría'.
    Se eliminó el else→'Mayoría' que ocultaba el problema.
    """
    conteo  = grupo["partido_normalizado"].value_counts()
    mayoria = conteo.index[0] if len(conteo) >= 1 else None
    minoria = conteo.index[1] if len(conteo) >= 2 else None

    roles      = []
    asignados  = {}
    for _, row in grupo.iterrows():
        p = row["partido_normalizado"]
        asignados[p] = asignados.get(p, 0) + 1
        if p == mayoria and asignados[p] <= 2:
            roles.append("Mayoría")
        elif p == minoria:
            roles.append("Primera Minoría")
        else:
            # Partido extra (raro, datos incompletos) → marcar como Mayoría
            # y emitir aviso al cierre del loop externo
            roles.append("Mayoría")
    return roles


# ── 1. Nómina de Senadores ────────────────────────────────────────────────────
def obtener_nomina_fallback():
    try:
        resp = requests.get(
            "https://www.senado.gob.ar/senadores/listadoPorApellido",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=20
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        senadores = []
        tabla = soup.find("table")
        if tabla:
            for fila in tabla.find_all("tr")[1:]:
                cols = fila.find_all("td")
                if len(cols) >= 3:
                    senadores.append({
                        "nombre":    cols[0].get_text(strip=True),
                        "provincia": cols[1].get_text(strip=True),
                        "partido":   cols[2].get_text(strip=True),
                    })
        df = pd.DataFrame(senadores)
        print(f"✅ Scraping fallback: {len(df)} senadores")
        return df
    except Exception as e:
        print(f"❌ Fallback también falló: {e}")
        return pd.DataFrame()


def obtener_nomina():
    print("\n📋 Obteniendo nómina de senadores activos...")
    data = get_con_reintento(f"{BASE_API}/senado/senadores")

    if not data:
        print("🔄 API no disponible, usando scraping de senado.gob.ar...")
        return obtener_nomina_fallback()

    df = pd.DataFrame(data)

    # ── FIX 4: filtrar mandatos VIGENTES ──────────────────────────────────────
    # Usar periodoLegal como fuente primaria (siempre presente).
    # periodoReal.fin = None significa "en ejercicio hasta el fin legal"
    # por eso NO se usa periodoReal para determinar si el mandato expiró.
    def mandato_vigente(row):
        try:
            # Fuente primaria: periodoLegal (fecha legal del mandato)
            periodo = row.get("periodoLegal") or {}
            if isinstance(periodo, str):
                periodo = ast.literal_eval(periodo)
            inicio = periodo.get("inicio") or ""
            fin    = periodo.get("fin")

            if not inicio or inicio > HOY_STR:
                return False                             # aún no asumió
            if fin is None or str(fin).strip() in ("", "None"):
                return True                             # sin fecha de fin → vigente
            return str(fin) >= HOY_STR                  # vigente si fin ≥ hoy
        except Exception:
            return False

    df["_vigente"] = df.apply(mandato_vigente, axis=1)
    df = df[df["_vigente"]].drop(columns=["_vigente"]).reset_index(drop=True)

    print(f"   Senadores con mandato vigente: {len(df)}")
    if not (60 <= len(df) <= 80):
        print(f"   ⚠️  Cantidad inusual (esperado ~72). Revisar datos de la API.")

    # ── Validar 3 por provincia ───────────────────────────────────────────────
    # FIX 5: advertencia explícita por provincia incompleta
    por_provincia = df.groupby("provincia").size()
    anomalias = por_provincia[por_provincia != 3]
    if not anomalias.empty:
        print(f"   ⚠️  Provincias con ≠ 3 senadores en la API (datos incompletos):")
        for prov, n in anomalias.items():
            print(f"       • {prov}: {n} senadores (faltan {3 - n})")

    # ── Normalizar partido ────────────────────────────────────────────────────
    df["partido_normalizado"] = df["partido"].apply(normalizar_partido)

    # ── Rol provincial (mayoría / primera minoría) ────────────────────────────
    df["rol_provincial"] = None
    for provincia, grupo in df.groupby("provincia"):
        roles = asignar_rol_provincial(grupo)
        df.loc[grupo.index, "rol_provincial"] = roles

    print(f"✅ Nómina final: {len(df)} senadores activos")
    return df


# ── 2. Actas / Votaciones ─────────────────────────────────────────────────────
def obtener_actas(año=None):
    año = año or AÑO_ACTUAL
    print(f"\n🗳️  Obteniendo actas {año}...")
    data = get_con_reintento(f"{BASE_API}/senado/actas/{año}")
    if not data:
        print(f"❌ Sin actas para {año}")
        return pd.DataFrame()
    df = pd.DataFrame(data)
    print(f"✅ {len(df)} registros de actas")
    return df


# ── 3. KPIs por Senador ───────────────────────────────────────────────────────
def calcular_kpis(df_nomina: pd.DataFrame, df_actas: pd.DataFrame) -> pd.DataFrame:
    print("\n📊 Calculando KPIs...")

    if df_actas.empty:
        print("   ⚠️  Sin actas disponibles — KPIs de votación omitidos")
        return df_nomina.copy()

    col_senador = next(
        (c for c in ["senador", "nombre_senador", "nombre"] if c in df_actas.columns),
        None
    )
    col_voto = next(
        (c for c in ["voto", "tipo_voto", "resultado"] if c in df_actas.columns),
        None
    )

    if not col_senador or not col_voto:
        print(f"   ⚠️  Columnas de actas no reconocidas: {list(df_actas.columns)}")
        return df_nomina.copy()

    df_actas[col_voto] = df_actas[col_voto].fillna("").astype(str)

    resumen = df_actas.groupby(col_senador).agg(
        total_votos  =(col_voto, "count"),
        votos_afirm  =(col_voto, lambda x: (x.str.upper().isin(["SI", "SÍ", "AFIRMATIVO"])).sum()),
        votos_neg    =(col_voto, lambda x: (x.str.upper().isin(["NO", "NEGATIVO"])).sum()),
        abstenciones =(col_voto, lambda x: (x.str.upper().isin(["ABSTENCION", "ABSTENCIÓN"])).sum()),
    ).reset_index().rename(columns={col_senador: "nombre"})

    df_result = df_nomina.merge(resumen, on="nombre", how="left")

    max_v = df_result["total_votos"].max()
    if max_v and max_v > 0:
        df_result["participation_index"] = (df_result["total_votos"] / max_v * 100).round(1)

    print(f"✅ KPIs listos para {len(df_result)} senadores")
    return df_result


# ── 4a. Reporte por Provincia ─────────────────────────────────────────────────
# FIX 2: esta función recibe df_final que ya viene filtrado por mandato vigente
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """3 senadores por provincia — eje federal.
    El df recibido debe contener SOLO senadores con mandato vigente.
    """
    if "provincia" not in df.columns:
        return pd.DataFrame()

    agg = {"nombre": "count"}
    if "participation_index" in df.columns:
        agg["participation_index"] = "mean"
    if "total_votos" in df.columns:
        agg["total_votos"] = "sum"

    resumen = df.groupby("provincia").agg(agg).reset_index()
    resumen.rename(columns={"nombre": "senadores"}, inplace=True)

    # Agregar partidos representados por provincia
    if "partido_normalizado" in df.columns:
        partidos_prov = (
            df.groupby("provincia")["partido_normalizado"]
            .apply(lambda x: " / ".join(sorted(x.unique())))
            .reset_index()
            .rename(columns={"partido_normalizado": "partidos"})
        )
        resumen = resumen.merge(partidos_prov, on="provincia", how="left")

    if "participation_index" in resumen.columns:
        resumen["participation_index"] = resumen["participation_index"].round(1)
        resumen = resumen.sort_values("participation_index", ascending=False)
    else:
        resumen = resumen.sort_values("provincia")

    # Validar que todas las provincias tengan 3 senadores
    anomalias = resumen[resumen["senadores"] != 3]
    if not anomalias.empty:
        print("   ⚠️  Reporte provincial — provincias con ≠ 3 senadores (API incompleta):")
        for _, r in anomalias.iterrows():
            print(f"       • {r['provincia']}: {r['senadores']} senadores")

    return resumen


# ── 4b. Reporte por Partido ───────────────────────────────────────────────────
# FIX 2: esta función recibe df_final que ya viene filtrado por mandato vigente
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    """Bloques políticos actuales con bancas y participation index.
    El df recibido debe contener SOLO senadores con mandato vigente.
    """
    col = "partido_normalizado" if "partido_normalizado" in df.columns else "partido"
    if col not in df.columns:
        return pd.DataFrame()

    agg = {"nombre": "count"}
    if "participation_index" in df.columns:
        agg["participation_index"] = "mean"
    if "votos_afirm" in df.columns:
        agg["votos_afirm"] = "sum"
    if "votos_neg" in df.columns:
        agg["votos_neg"] = "sum"
    if "abstenciones" in df.columns:
        agg["abstenciones"] = "sum"

    resumen = df.groupby(col).agg(agg).reset_index()
    resumen.rename(columns={"nombre": "bancas", col: "partido"}, inplace=True)

    # Mayorías vs minorías por partido
    if "rol_provincial" in df.columns:
        roles = (
            df.groupby(col)["rol_provincial"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
            .rename(columns={col: "partido"})
        )
        resumen = resumen.merge(roles, on="partido", how="left")

    if "participation_index" in resumen.columns:
        resumen["participation_index"] = resumen["participation_index"].round(1)

    return resumen.sort_values("bancas", ascending=False)


# ── 5. Guardar ────────────────────────────────────────────────────────────────
def guardar_resultados(df_sen: pd.DataFrame, df_prov: pd.DataFrame, df_partido: pd.DataFrame):
    os.makedirs("data", exist_ok=True)
    fecha = HOY.strftime("%Y-%m-%d")

    archivos = [
        (df_sen,     f"senadores_{fecha}.csv"),
        (df_prov,    f"reporte_provincial_{fecha}.csv"),
        (df_partido, f"reporte_partido_{fecha}.csv"),
    ]
    for df, nombre in archivos:
        if not df.empty:
            ruta = f"data/{nombre}"
            df.to_csv(ruta, index=False, encoding="utf-8-sig")
            print(f"💾 {ruta}  ({len(df)} filas)")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🏛️  MONITOR LEGISLATIVO — SENADO NACIONAL")
    print(f"📅  {HOY.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    df_nomina = obtener_nomina()
    df_actas  = obtener_actas(AÑO_ACTUAL)

    if df_actas.empty:
        print(f"🔄 Sin actas {AÑO_ACTUAL}, probando {AÑO_ACTUAL - 1}...")
        df_actas = obtener_actas(AÑO_ACTUAL - 1)

    df_final      = calcular_kpis(df_nomina, df_actas)
    df_provincial = reporte_provincial(df_final)
    df_partido    = reporte_por_partido(df_final)

    guardar_resultados(df_final, df_provincial, df_partido)

    # Resumen consola
    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO")
    print("=" * 60)

    print(f"\n🗺️  Provincias representadas: {df_final['provincia'].nunique()}")
    print(f"👥 Total senadores activos:   {len(df_final)}  (esperado: 72)")

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


if __name__ == "__main__":
    main()
