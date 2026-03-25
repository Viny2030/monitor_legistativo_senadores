"""
scraper_senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina
72 senadores: 3 por cada una de las 24 provincias/CABA
  - 2 bancas → partido ganador (mayoría)
  - 1 banca  → primera minoría
Fuentes: ArgentinaDatos API + senado.gob.ar (fallback scraping)
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
AÑO_ACTUAL = HOY.year

BLOQUES_MAP = {
    "Unión por la Patria":         ["alianza unión por la patria", "frente de todos",
                                    "alianza frente de todos", "frente todos",
                                    "frente para la victoria", "alianza frente para la victoria",
                                    "peronista", "justicialista"],
    "La Libertad Avanza":          ["alianza la libertad avanza", "libertad avanza"],
    "Unión Cívica Radical":        ["unión cívica radical", "u. c. r. del pueblo",
                                    "juntos por el cambio", "alianza cambiemos"],
    "Pro / Cambiemos":             ["pro", "alianza unión pro", "cambiemos buenos aires"],
    "Movimiento Popular Neuquino": ["movimiento popular neuquino"],
}


# ── Utilidades ────────────────────────────────────────────────────────────────
def get_con_reintento(url, intentos=3, espera=5):
    for i in range(intentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 502:
                print(f"⚠️  Error 502. Reintento {i+1}/{intentos} en {espera}s...")
                time.sleep(espera)
            else:
                print(f"⚠️  HTTP {resp.status_code} — {url}")
                return None
        except Exception as e:
            print(f"❌ Conexión fallida (intento {i+1}): {e}")
            time.sleep(espera)
    return None


def normalizar_partido(p):
    if not isinstance(p, str):
        return "Otro"
    p_lower = p.strip().lower()
    for bloque, variantes in BLOQUES_MAP.items():
        if any(v in p_lower for v in variantes):
            return bloque
    return p.strip()


def asignar_rol_provincial(grupo):
    """
    Dentro de cada provincia asigna:
      - 'Mayoría'          → los 2 senadores del partido ganador
      - 'Primera Minoría'  → el senador del partido que salió segundo
    """
    conteo = grupo["partido_normalizado"].value_counts()
    mayoria = conteo.index[0] if len(conteo) >= 1 else None
    minoria = conteo.index[1] if len(conteo) >= 2 else None
    roles = []
    asignados = {}
    for _, row in grupo.iterrows():
        p = row["partido_normalizado"]
        asignados[p] = asignados.get(p, 0) + 1
        if p == mayoria and asignados[p] <= 2:
            roles.append("Mayoría")
        elif p == minoria:
            roles.append("Primera Minoría")
        else:
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
    hoy_str = HOY.strftime("%Y-%m-%d")

    # ── Filtrar mandatos VIGENTES ─────────────────────────────────────────────
    def mandato_vigente(row):
        try:
            periodo = row.get("periodoReal") or row.get("periodoLegal") or {}
            if isinstance(periodo, str):
                periodo = ast.literal_eval(periodo)
            inicio = periodo.get("inicio") or ""
            fin    = periodo.get("fin")
            if not inicio or inicio > hoy_str:
                return False
            if fin is None or str(fin).strip() in ("", "None"):
                return True
            return str(fin) >= hoy_str
        except Exception:
            return False

    df["_vigente"] = df.apply(mandato_vigente, axis=1)
    df = df[df["_vigente"]].drop(columns=["_vigente"]).reset_index(drop=True)

    print(f"   Senadores con mandato vigente: {len(df)}")
    if not (60 <= len(df) <= 80):
        print(f"   ⚠️  Cantidad inusual (esperado ~72). Revisar filtro.")

    # ── Validar 3 por provincia ───────────────────────────────────────────────
    por_provincia = df.groupby("provincia").size()
    anomalias = por_provincia[por_provincia != 3]
    if not anomalias.empty:
        print(f"   ⚠️  Provincias con ≠ 3 senadores:\n{anomalias.to_string()}")

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

    if df_actas.empty or df_nomina.empty:
        print("⚠️  Datos insuficientes, devolviendo nómina sin KPIs")
        return df_nomina

    col_senador = next(
        (c for c in df_actas.columns if any(k in c.lower() for k in ["nombre", "senador", "legislador"])),
        None
    )
    col_voto = next(
        (c for c in df_actas.columns if "voto" in c.lower()),
        None
    )

    if col_senador and col_voto:
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
    else:
        df_result = df_nomina.copy()

    print(f"✅ KPIs listos para {len(df_result)} senadores")
    return df_result


# ── 4a. Reporte por Provincia ─────────────────────────────────────────────────
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """3 senadores por provincia — eje federal."""
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

    return resumen


# ── 4b. Reporte por Partido ───────────────────────────────────────────────────
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    """Bloques políticos actuales con bancas y participation index."""
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

    df_nomina     = obtener_nomina()
    df_actas      = obtener_actas(AÑO_ACTUAL)

    if df_actas.empty:
        print(f"🔄 Sin actas {AÑO_ACTUAL}, probando {AÑO_ACTUAL - 1}...")
        df_actas  = obtener_actas(AÑO_ACTUAL - 1)

    df_final      = calcular_kpis(df_nomina, df_actas)
    df_provincial = reporte_provincial(df_final)
    df_partido    = reporte_por_partido(df_final)

    guardar_resultados(df_final, df_provincial, df_partido)

    # Resumen consola
    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO")
    print("=" * 60)

    print(f"\n🗺️  Provincias representadas: {df_final['provincia'].nunique()}")
    print(f"👥 Total senadores activos:   {len(df_final)}")

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

    print("\n✅ Proceso completado")


if __name__ == "__main__":
    main()
