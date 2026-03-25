"""
scraper_senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina
Fuentes: ArgentinaDatos API + senado.gob.ar (fallback scraping)
"""

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


# ── Utilidad: GET con reintentos ───────────────────────────────────────────────
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


# ── 1. Nómina de Senadores ────────────────────────────────────────────────────
def obtener_nomina():
    print("\n📋 Obteniendo nómina de senadores...")
    data = get_con_reintento(f"{BASE_API}/senado/senadores")

    if data:
        df = pd.DataFrame(data)
        print(f"✅ API ArgentinaDatos: {len(df)} senadores")
        return df

    print("🔄 API no disponible, usando scraping de senado.gob.ar...")
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
    if "provincia" not in df.columns:
        return pd.DataFrame()

    agg = {"nombre": "count"}
    if "participation_index" in df.columns:
        agg["participation_index"] = "mean"
    if "total_votos" in df.columns:
        agg["total_votos"] = "sum"

    resumen = df.groupby("provincia").agg(agg).reset_index()
    resumen.rename(columns={"nombre": "senadores"}, inplace=True)
    if "participation_index" in resumen.columns:
        resumen["participation_index"] = resumen["participation_index"].round(1)

    return resumen.sort_values("participation_index", ascending=False) \
                  if "participation_index" in resumen.columns \
                  else resumen.sort_values("provincia")


# ── 4b. Reporte por Partido ───────────────────────────────────────────────────
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    if "partido" not in df.columns:
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

    resumen = df.groupby("partido").agg(agg).reset_index()
    resumen.rename(columns={"nombre": "senadores"}, inplace=True)
    if "participation_index" in resumen.columns:
        resumen["participation_index"] = resumen["participation_index"].round(1)

    return resumen.sort_values("senadores", ascending=False)


# ── 5. Guardar ────────────────────────────────────────────────────────────────
def guardar_resultados(df_sen, df_prov, df_partido):
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

    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO")
    print("=" * 60)

    if "partido" in df_final.columns:
        print(f"\n🏛️  Por Partido:\n{df_final['partido'].value_counts().to_string()}")

    if "provincia" in df_final.columns:
        print(f"\n🗺️  Provincias representadas: {df_final['provincia'].nunique()}")

    if not df_provincial.empty:
        print(f"\n📊 Top Provincias:\n{df_provincial.head(10).to_string(index=False)}")

    if not df_partido.empty:
        print(f"\n🗳️  Por Partido:\n{df_partido.to_string(index=False)}")

    print("\n✅ Proceso completado")


if __name__ == "__main__":
    main()
