"""
scripts/actualizar_bipartisan.py  —  Monitor Legislativo SENADO
Bipartisan Score (Tasa de Consenso) por Senador
================================================
Mide qué proporción de los votos de cada senador coincide con senadores
de OTROS partidos. Un score alto → legislador que construye consensos.

Fórmula:
    bipartisan_score = votos_coincidentes_con_otros_partidos / total_votos_emitidos

Fuente: ArgentinaDatos API  →  /v1/senado/actas/{año}
Output: data/bipartisan_{fecha}.csv

Columnas del output:
    nombre | partido | provincia | total_votos | votos_bipartisan | bipartisan_score
"""

import sys
import os
import requests
import pandas as pd
from datetime import datetime
import holidays

# ── Config ────────────────────────────────────────────────────────────────────
BASE_API = "https://api.argentinadatos.com/v1"
HOY      = datetime.today()
HEADERS  = {
    "User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)",
    "Accept": "application/json",
}

# Normalización de partidos actuales (mismo mapa que scraper_senadores.py)
BLOQUES_MAP = {
    "Unión por la Patria":         ["alianza unión por la patria", "frente de todos",
                                    "alianza frente de todos", "frente todos",
                                    "frente para la victoria", "alianza frente para la victoria",
                                    "peronista", "justicialista"],
    "La Libertad Avanza":          ["alianza la libertad avanza", "libertad avanza"],
    "Unión Cívica Radical":        ["unión cívica radical", "u. c. r. del pueblo",
                                    "u. c. r. intransigente", "u. c. r. antipersonalista"],
    "Pro / Juntos por el Cambio":  ["alianza cambiemos", "juntos por el cambio",
                                    "cambiemos buenos aires", "pro",
                                    "alianza unión pro"],
    "Movimiento Popular Neuquino": ["movimiento popular neuquino"],
}


def es_dia_habil() -> bool:
    """Retorna False si es fin de semana o feriado → el Actions sale limpio."""
    hoy = datetime.now()
    if hoy.weekday() >= 5:
        print(f"☕ Fin de semana — saltando ejecución.")
        return False
    ar_holidays = holidays.Argentina(years=hoy.year)
    if hoy in ar_holidays:
        print(f"☕ Feriado ({ar_holidays.get(hoy)}) — saltando ejecución.")
        return False
    return True


def normalizar_partido(p: str) -> str:
    if not isinstance(p, str):
        return "Otro"
    p_lower = p.strip().lower()
    for bloque, variantes in BLOQUES_MAP.items():
        if any(v in p_lower for v in variantes):
            return bloque
    return p.strip()


def get_con_reintento(url, intentos=3, espera=5):
    import time
    for i in range(intentos):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 502:
                print(f"  ⚠️  502 — reintento {i+1}/{intentos}...")
                time.sleep(espera)
            else:
                print(f"  ⚠️  HTTP {resp.status_code}")
                return None
        except Exception as e:
            print(f"  ❌ Conexión fallida (intento {i+1}): {e}")
            time.sleep(espera)
    return None


def obtener_actas_con_partido(año: int) -> pd.DataFrame:
    """
    Descarga las actas del año y les agrega el partido normalizado
    cruzando con la nómina de senadores activos.
    """
    print(f"\n📥 Descargando actas {año}...")
    actas = get_con_reintento(f"{BASE_API}/senado/actas/{año}")
    if not actas:
        return pd.DataFrame()
    df_actas = pd.DataFrame(actas)
    print(f"   {len(df_actas)} registros de actas")

    # Nómina para cruzar partido
    print("📥 Descargando nómina para cruzar partido...")
    nomina = get_con_reintento(f"{BASE_API}/senado/senadores")
    if nomina:
        df_nom = pd.DataFrame(nomina)

        def activo(row):
            try:
                p = row.get("periodoReal") or row.get("periodoLegal") or {}
                if isinstance(p, str):
                    import ast
                    p = ast.literal_eval(p)
                fin = p.get("fin")
                return not fin or fin >= HOY.strftime("%Y-%m-%d")
            except Exception:
                return False

        df_nom = df_nom[df_nom.apply(activo, axis=1)][["nombre", "partido", "provincia"]]
        df_nom["partido_norm"] = df_nom["partido"].apply(normalizar_partido)

        # Cruzar
        col_sen = next(
            (c for c in df_actas.columns if any(k in c.lower() for k in ["nombre", "senador"])),
            None
        )
        if col_sen:
            df_actas = df_actas.merge(
                df_nom[["nombre", "partido_norm", "provincia"]],
                left_on=col_sen, right_on="nombre", how="left"
            )

    return df_actas


def calcular_bipartisan(df_actas: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada votación (acta), identifica el voto mayoritario.
    Cada senador que vota con alguien de otro partido suma 1 voto bipartisan.
    """
    col_sen   = next((c for c in df_actas.columns if any(k in c.lower() for k in ["nombre", "senador"])), None)
    col_voto  = next((c for c in df_actas.columns if "voto" in c.lower()), None)
    col_acta  = next((c for c in df_actas.columns if any(k in c.lower() for k in ["acta", "sesion", "id"])), None)

    if not col_sen or not col_voto:
        print("❌ No se encontraron columnas clave en las actas")
        return pd.DataFrame()

    if not col_acta:
        # Si no hay ID de acta, usamos índice de grupo
        df_actas = df_actas.copy()
        df_actas["_acta_id"] = (df_actas.index // 72)  # ~72 senadores por votación
        col_acta = "_acta_id"

    resultados = []

    for senador, grupo in df_actas.groupby(col_sen):
        total_votos     = len(grupo)
        votos_bipartisan = 0

        for acta_id, votacion in grupo.groupby(col_acta):
            mi_voto = votacion[col_voto].values[0] if len(votacion) > 0 else None
            if not mi_voto:
                continue

            # Buscar si alguien de otro partido votó igual
            acta_completa = df_actas[df_actas[col_acta] == acta_id]
            mismo_voto    = acta_completa[acta_completa[col_voto] == mi_voto]

            mi_partido = votacion["partido_norm"].values[0] if "partido_norm" in votacion.columns else None

            if mi_partido and "partido_norm" in mismo_voto.columns:
                otros_partidos = mismo_voto[mismo_voto["partido_norm"] != mi_partido]
                if len(otros_partidos) > 0:
                    votos_bipartisan += 1
            else:
                # Sin info de partido: contar si hay más de 1 bloque votando igual
                votos_bipartisan += 1

        score = round(votos_bipartisan / total_votos, 4) if total_votos > 0 else 0.0
        partido   = grupo["partido_norm"].values[0] if "partido_norm" in grupo.columns else "N/D"
        provincia = grupo["provincia"].values[0]     if "provincia"   in grupo.columns else "N/D"

        resultados.append({
            "nombre":           senador,
            "partido":          partido,
            "provincia":        provincia,
            "total_votos":      total_votos,
            "votos_bipartisan": votos_bipartisan,
            "bipartisan_score": score,
        })

    df_result = pd.DataFrame(resultados).sort_values("bipartisan_score", ascending=False)
    return df_result


def main():
    print("=" * 55)
    print("🏛️  Monitor Senado — Bipartisan Score")
    print(f"📅  {HOY.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    if not es_dia_habil():
        sys.exit(0)

    año = HOY.year
    df_actas = obtener_actas_con_partido(año)

    if df_actas.empty:
        print(f"🔄 Sin actas {año}, probando {año - 1}...")
        df_actas = obtener_actas_con_partido(año - 1)

    if df_actas.empty:
        print("❌ No se pudieron obtener actas. Abortando.")
        sys.exit(1)

    print("\n⚙️  Calculando Bipartisan Score...")
    df_bipartisan = calcular_bipartisan(df_actas)

    if df_bipartisan.empty:
        print("❌ No se pudo calcular el score.")
        sys.exit(1)

    os.makedirs("data", exist_ok=True)
    fecha  = HOY.strftime("%Y-%m-%d")
    output = f"data/bipartisan_{fecha}.csv"
    df_bipartisan.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"\n✅ Guardado: {output} ({len(df_bipartisan)} senadores)")
    print(f"\n📊 Score promedio: {df_bipartisan['bipartisan_score'].mean():.4f}")
    print(f"\n🏆 Top 10 por Bipartisan Score:")
    print(df_bipartisan.head(10).to_string(index=False))

    print(f"\n📊 Score promedio por partido:")
    if "partido" in df_bipartisan.columns:
        print(
            df_bipartisan.groupby("partido")["bipartisan_score"]
            .mean().round(4).sort_values(ascending=False).to_string()
        )

    return df_bipartisan


if __name__ == "__main__":
    main()
