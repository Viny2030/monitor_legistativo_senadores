"""
scraper_senadores.py
Monitor Legislativo — Cámara de Senadores de la Nación Argentina
Fuentes: ArgentinaDatos API + senado.gob.ar (fallback scraping)
Clasificadores: partido político + provincia de origen
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
    """GET robusto para APIs gubernamentales inestables."""
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
    """
    Obtiene los 72 senadores desde ArgentinaDatos.
    Campos clave: nombre, provincia, partido, periodoLegal, foto, email
    Fallback: scraping directo de senado.gob.ar
    """
    print("\n📋 Obteniendo nómina de senadores...")
    data = get_con_reintento(f"{BASE_API}/senado/senadores")

    if data:
        df = pd.DataFrame(data)
        # Normalizar columnas clave
        if "periodoLegal" in df.columns:
            df["periodo_inicio"] = df["periodoLegal"].apply(
                lambda x: x.get("inicio", "") if isinstance(x, dict) else ""
            )
            df["periodo_fin"] = df["periodoLegal"].apply(
                lambda x: x.get("fin", "") if isinstance(x, dict) else ""
            )
            df.drop(columns=["periodoLegal", "periodoReal"], errors="ignore", inplace=True)
        # Limpiar columnas no necesarias
        df.drop(columns=["redes", "reemplazo", "observaciones"], errors="ignore", inplace=True)
        print(f"✅ API ArgentinaDatos: {len(df)} senadores")
        return df

    # Fallback: scraping directo
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
                        "nombre":   cols[0].get_text(strip=True),
                        "provincia": cols[1].get_text(strip=True),
                        "partido":  cols[2].get_text(strip=True),
                    })
        df = pd.DataFrame(senadores)
        print(f"✅ Scraping fallback: {len(df)} senadores")
        return df
    except Exception as e:
        print(f"❌ Fallback también falló: {e}")
        return pd.DataFrame()


# ── 2. Actas / Votaciones ─────────────────────────────────────────────────────
def obtener_actas(año=None):
    """Obtiene las actas de votación nominales del año indicado."""
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
    """
    KPIs calculados por senador:
    - total_votos:         cantidad de veces que votó
    - votos_afirm:         votos afirmativos
    - votos_neg:           votos negativos
    - abstenciones:        abstenciones
    - participation_index: % relativo al senador más activo (0–100)
    """
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
            total_votos =(col_voto, "count"),
            votos_afirm =(col_voto, lambda x: (x.str.upper().isin(["SI", "SÍ", "AFIRMATIVO"])).sum()),
            votos_neg   =(col_voto, lambda x: (x.str.upper().isin(["NO", "NEGATIVO"])).sum()),
            abstenciones=(col_voto, lambda x: (x.str.upper().isin(["ABSTENCION", "ABSTENCIÓN"])).sum()),
        ).reset_index().rename(columns={col_senador: "nombre"})

        df_result = df_nomina.merge(resumen, on="nombre", how="left")

        # Participation Index (0–100)
        max_v = df_result["total_votos"].max()
        if pd.notna(max_v) and max_v > 0:
            df_result["participation_index"] = (
                df_result["total_votos"] / max_v * 100
            ).round(1)
    else:
        print("⚠️  No se encontraron columnas de senador/voto en actas")
        df_result = df_nomina.copy()

    print(f"✅ KPIs listos para {len(df_result)} senadores")
    return df_result


# ── 4a. Reporte por Provincia ─────────────────────────────────────────────────
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por provincia — eje federal del Senado.
    Cada provincia tiene exactamente 3 senadores.
    """
    if "provincia" not in df.columns:
        print("⚠️  Columna 'provincia' no encontrada")
        return pd.DataFrame()

    agg = {"nombre": "count"}
    if "participation_index" in df.columns:
        agg["participation_index"] = "mean"
    if "total_votos" in df.columns:
        agg["total_votos"] = "sum"
    if "votos_afirm" in df.columns:
        agg["votos_afirm"] = "sum"

    resumen = df.groupby("provincia").agg(agg).reset_index()
    resumen.rename(columns={"nombre": "senadores"}, inplace=True)
    if "participation_index" in resumen.columns:
        resumen["participation_index"] = resumen["participation_index"].round(1)
        resumen = resumen.sort_values("participation_index", ascending=False)
    else:
        resumen = resumen.sort_values("provincia")

    return resumen


# ── 4b. Reporte por Partido ───────────────────────────────────────────────────
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por partido político — eje de bloques del Senado.
    Permite ver qué bloques votan más y cómo votan.
    """
    if "partido" not in df.columns:
        print("⚠️  Columna 'partido' no encontrada")
        return pd.DataFrame()

    agg = {"nombre": "count"}
    if "participation_index" in df.columns:
        agg["participation_index"] = "mean"
    if "total_votos" in df.columns:
        agg["total_votos"] = "sum"
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


# ── 5. Guardar resultados ─────────────────────────────────────────────────────
def guardar_resultados(df_sen: pd.DataFrame, df_prov: pd.DataFrame, df_partido: pd.DataFrame):
    """Guarda los 3 reportes CSV en la carpeta data/"""
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
        else:
            print(f"⚠️  Sin datos para {nombre}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🏛️  MONITOR LEGISLATIVO — SENADO NACIONAL")
    print(f"📅  {HOY.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    # 1. Nómina base
    df_nomina = obtener_nomina()

    # 2. Actas del año actual (fallback al año anterior)
    df_actas = obtener_actas(AÑO_ACTUAL)
    if df_actas.empty:
        print(f"🔄 Sin actas {AÑO_ACTUAL}, probando {AÑO_ACTUAL - 1}...")
        df_actas = obtener_actas(AÑO_ACTUAL - 1)

    # 3. KPIs individuales
    df_final = calcular_kpis(df_nomina, df_actas)

    # 4. Reportes por clasificador
    df_provincial = reporte_provincial(df_final)
    df_partido    = reporte_por_partido(df_final)

    # 5. Guardar CSV
    guardar_resultados(df_final, df_provincial, df_partido)

    # 6. Resumen en consola
    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO")
    print("=" * 60)

    if "partido" in df_final.columns:
        print(f"\n🏛️  Senadores por Partido:\n{df_final['partido'].value_counts().to_string()}")

    if "provincia" in df_final.columns:
        print(f"\n🗺️  Provincias representadas: {df_final['provincia'].nunique()}")

    if not df_provincial.empty:
        print(f"\n📊 Ranking Provincial (participation_index):")
        print(df_provincial.to_string(index=False))

    if not df_partido.empty:
        print(f"\n🗳️  Ranking por Partido:")
        print(df_partido.to_string(index=False))

    print("\n✅ Proceso completado exitosamente")


if __name__ == "__main__":
    main()
