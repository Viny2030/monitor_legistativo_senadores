"""
pipeline_senado.py
Monitor Legislativo — pipeline de Senadores

Orquesta:
  1. scrapers/senadores.py  → nómina 72 senadores + actas
  2. core/senado.py         → KPIs, reportes provincial y por partido
  3. Guarda CSVs en data/

Corre standalone o es llamado desde el pipeline general.
"""

import sys
import os
import time
from datetime import datetime

# Permitir imports relativos cuando se corre desde la raíz del repo
sys.path.insert(0, os.path.dirname(__file__))

from scrapers.senadores import obtener_nomina, obtener_actas, ANIO_ACTUAL
from core.senado import (
    calcular_kpis,
    reporte_provincial,
    reporte_por_partido,
    resumen_camara,
    guardar_resultados,
)

HOY = datetime.today()


def main():
    print("=" * 60)
    print("🏛️  Monitor Legislativo — Senado Nacional")
    print(f"📅  Fecha: {HOY.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    # ── 1. Nómina ─────────────────────────────────────────────────────────────
    df_nomina = obtener_nomina(guardar_csv=False)
    if df_nomina.empty:
        print("❌ No se pudo obtener la nómina. Abortando.")
        sys.exit(1)

    # ── 2. Actas ──────────────────────────────────────────────────────────────
    time.sleep(0.5)
    df_actas = obtener_actas(ANIO_ACTUAL)
    if df_actas.empty:
        print(f"🔄 Sin actas {ANIO_ACTUAL}, probando {ANIO_ACTUAL - 1}...")
        time.sleep(1)
        df_actas = obtener_actas(ANIO_ACTUAL - 1)

    # ── 3. KPIs ───────────────────────────────────────────────────────────────
    df_final = calcular_kpis(df_nomina, df_actas)

    # ── 4. Reportes ───────────────────────────────────────────────────────────
    df_prov    = reporte_provincial(df_final)
    df_partido = reporte_por_partido(df_final)

    # ── 5. Guardar ────────────────────────────────────────────────────────────
    guardar_resultados(df_final, df_prov, df_partido)

    # ── 6. Resumen consola ────────────────────────────────────────────────────
    resumen = resumen_camara(df_final, df_partido)

    print("\n" + "=" * 60)
    print("📌 RESUMEN EJECUTIVO — SENADO")
    print("=" * 60)
    print(f"\n👥 Senadores activos      : {resumen['total_senadores']} / {resumen['esperado']}  "
          f"{'✅' if resumen['completo'] else '⚠️  INCOMPLETO'}")
    print(f"🗺️  Provincias             : {resumen['provincias']}")
    print(f"⚖️  Mayorías               : {resumen['bancas_mayoria']}  "
          f"(esperado 48)")
    print(f"⚖️  Primeras Minorías      : {resumen['bancas_primera_minoria']}  "
          f"(esperado 24)")
    print(f"🏆 Partido líder          : {resumen['partido_lider']} "
          f"({resumen['bancas_lider']} bancas)")
    if resumen["participation_pct_avg"]:
        print(f"📊 Participación promedio : {resumen['participation_pct_avg']}%")
    if resumen["proximas_renovaciones"]:
        print(f"🗓️  Próximas renovaciones  : {' → '.join(resumen['proximas_renovaciones'])}")

    print(f"\n🗳️  Bancas por Partido:")
    print(df_partido[["partido", "bancas", "Mayoría", "Primera Minoría"]].to_string(index=False)
          if "Mayoría" in df_partido.columns
          else df_partido[["partido", "bancas"]].to_string(index=False))

    print(f"\n📊 Reporte Provincial (top 10 por participación):")
    cols_prov = ["provincia", "senadores", "partidos"]
    if "participation_pct" in df_prov.columns:
        cols_prov.append("participation_pct")
    print(df_prov[cols_prov].head(10).to_string(index=False))

    return {
        "nomina":    df_final,
        "provincial": df_prov,
        "partido":   df_partido,
        "resumen":   resumen,
    }


if __name__ == "__main__":
    main()
