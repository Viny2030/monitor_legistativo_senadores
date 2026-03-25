"""
core/senado.py
Monitor Legislativo — KPIs y reportes de la Cámara de Senadores

Calcula los mismos indicadores que Diputados pero ajustados
a la lógica del Senado (72 bancas, 3 por provincia, renovación por tercios).

Funciones principales:
  - calcular_kpis(df_nomina, df_actas)  → participation_pct por senador
  - reporte_provincial(df)              → 1 fila por provincia (3 senadores)
  - reporte_por_partido(df)             → bancas / Mayoría / Primera Minoría
  - resumen_camara(df, df_partido)      → métricas globales de la cámara
"""

import pandas as pd
from datetime import datetime

HOY = datetime.today()
HOY_ISO = HOY.strftime("%Y-%m-%d")

BANCAS_SENADO    = 72
PROVINCIAS_TOTAL = 24   # 23 provincias + CABA


# ── KPIs de participación ─────────────────────────────────────────────────────
def calcular_kpis(df_nomina: pd.DataFrame,
                  df_actas:  pd.DataFrame) -> pd.DataFrame:
    """
    Cruza nómina con actas de votación para calcular KPIs de participación.
    Si no hay actas disponibles devuelve la nómina con columnas KPI en 0.

    Columns KPI agregadas:
      votos_total, votos_afirmativos, votos_negativos,
      abstenciones, ausencias, participation_pct
    """
    cols_kpi = ["votos_total", "votos_afirmativos", "votos_negativos",
                "abstenciones", "ausencias", "participation_pct"]

    if df_actas.empty or "votos" not in df_actas.columns:
        df = df_nomina.copy()
        for c in cols_kpi:
            df[c] = 0 if c != "participation_pct" else 0.0
        return df

    # Expandir lista de votos en filas individuales
    filas = []
    for _, acta in df_actas.iterrows():
        for voto in (acta.get("votos") or []):
            filas.append({
                "nombre": voto.get("nombre", ""),
                "voto":   str(voto.get("voto", "")).lower().strip(),
            })
    df_votos = pd.DataFrame(filas)

    if df_votos.empty:
        df = df_nomina.copy()
        for c in cols_kpi:
            df[c] = 0 if c != "participation_pct" else 0.0
        return df

    # Pivot de votos — la API usa minúsculas: "si", "no", "abstencion", "ausente"
    resumen = (
        df_votos.groupby("nombre")["voto"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
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

    total_sesiones = len(df_actas)
    resumen["participation_pct"] = (
        (resumen["votos_afirmativos"]
         + resumen["votos_negativos"]
         + resumen["abstenciones"])
        / total_sesiones * 100
    ).round(2)

    df_final = df_nomina.merge(resumen, on="nombre", how="left")
    for c in ["votos_total", "votos_afirmativos", "votos_negativos",
              "abstenciones", "ausencias"]:
        df_final[c] = df_final[c].fillna(0).astype(int)
    df_final["participation_pct"] = df_final["participation_pct"].fillna(0.0)

    return df_final


# ── Reporte provincial ────────────────────────────────────────────────────────
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega por provincia: senadores, partidos representados y participation_pct.
    Emite advertencia si alguna provincia tiene ≠ 3 senadores (dato faltante).
    """
    agg = {"nombre": "count"}
    if "participation_pct" in df.columns:
        agg["participation_pct"] = "mean"
    if "votos_total" in df.columns:
        agg["votos_total"] = "sum"

    rp = df.groupby("provincia").agg(agg).reset_index()
    rp.rename(columns={"nombre": "senadores"}, inplace=True)

    if "partido_normalizado" in df.columns:
        partidos = (
            df.groupby("provincia")["partido_normalizado"]
            .apply(lambda x: " / ".join(sorted(x.unique())))
            .reset_index()
            .rename(columns={"partido_normalizado": "partidos"})
        )
        rp = rp.merge(partidos, on="provincia", how="left")

    # Distribución de roles por provincia
    if "rol_provincial" in df.columns:
        roles = (
            df.groupby("provincia")["rol_provincial"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
        )
        rp = rp.merge(roles, on="provincia", how="left")

    if "participation_pct" in rp.columns:
        rp["participation_pct"] = rp["participation_pct"].round(1)
        rp = rp.sort_values("participation_pct", ascending=False)
    else:
        rp = rp.sort_values("provincia")

    # Advertencia de provincias incompletas
    incompletas = rp[rp["senadores"] != 3]
    if not incompletas.empty:
        print("\n⚠️  Provincias con ≠ 3 senadores (dato faltante en fuentes):")
        for _, row in incompletas.iterrows():
            print(f"   • {row['provincia']}: {row['senadores']} senador(es)")

    return rp.reset_index(drop=True)


# ── Reporte por partido ───────────────────────────────────────────────────────
def reporte_por_partido(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa por partido normalizado: bancas, Mayoría, Primera Minoría.
    Total bancas debe sumar 72.
    """
    col = "partido_normalizado" if "partido_normalizado" in df.columns else "partido"

    agg = {"nombre": "count"}
    if "participation_pct" in df.columns:
        agg["participation_pct"] = "mean"
    if "votos_afirmativos" in df.columns:
        agg["votos_afirmativos"] = "sum"
        agg["votos_negativos"]   = "sum"
        agg["abstenciones"]      = "sum"

    rp = df.groupby(col).agg(agg).reset_index()
    rp.rename(columns={"nombre": "bancas", col: "partido"}, inplace=True)

    if "rol_provincial" in df.columns:
        roles = (
            df.groupby(col)["rol_provincial"]
            .value_counts()
            .unstack(fill_value=0)
            .reset_index()
            .rename(columns={col: "partido"})
        )
        rp = rp.merge(roles, on="partido", how="left")

    if "participation_pct" in rp.columns:
        rp["participation_pct"] = rp["participation_pct"].round(1)

    rp = rp.sort_values("bancas", ascending=False).reset_index(drop=True)

    total = rp["bancas"].sum()
    if total != BANCAS_SENADO:
        print(f"⚠️  Reporte partido: {total} bancas (esperado {BANCAS_SENADO}, "
              f"faltan {BANCAS_SENADO - total})")

    return rp


# ── Resumen de cámara ─────────────────────────────────────────────────────────
def resumen_camara(df: pd.DataFrame,
                   df_partido: pd.DataFrame) -> dict:
    """
    Métricas globales de la Cámara de Senadores para el dashboard.
    """
    total = len(df)
    provincias = df["provincia"].nunique()

    roles = df["rol_provincial"].value_counts().to_dict() if "rol_provincial" in df.columns else {}
    mayoria_total = roles.get("Mayoría", 0)
    minoria_total = roles.get("Primera Minoría", 0)

    # Partido con más bancas
    partido_lider = (
        df_partido.iloc[0]["partido"] if not df_partido.empty else "N/D"
    )
    bancas_lider = int(df_partido.iloc[0]["bancas"]) if not df_partido.empty else 0

    # Participation promedio
    participation_avg = (
        round(df["participation_pct"].mean(), 1)
        if "participation_pct" in df.columns and df["participation_pct"].sum() > 0
        else None
    )

    # Próxima renovación (tercios: 24 bancas cada 2 años)
    # Los períodos que vencen más próximamente
    def _fin(s):
        try:
            import ast
            return ast.literal_eval(s).get("fin", "")
        except Exception:
            return ""

    df["_fin"] = df["periodoLegal"].apply(_fin)
    proxima_renovacion = sorted(df["_fin"].unique())
    proxima_renovacion = [f for f in proxima_renovacion if f > HOY_ISO]
    df.drop(columns=["_fin"], inplace=True)

    return {
        "total_senadores":        total,
        "esperado":               BANCAS_SENADO,
        "completo":               total == BANCAS_SENADO,
        "provincias":             provincias,
        "bancas_mayoria":         mayoria_total,
        "bancas_primera_minoria": minoria_total,
        "partido_lider":          partido_lider,
        "bancas_lider":           bancas_lider,
        "participation_pct_avg":  participation_avg,
        "proximas_renovaciones":  proxima_renovacion[:3],
        "partidos_representados": len(df_partido),
        "fecha_actualizacion":    HOY_ISO,
    }


# ── Guardar resultados ────────────────────────────────────────────────────────
def guardar_resultados(df_final:    pd.DataFrame,
                       df_prov:     pd.DataFrame,
                       df_partido:  pd.DataFrame,
                       carpeta:     str = "data") -> None:
    """Guarda los 3 CSVs de senadores en la carpeta data/."""
    import os
    os.makedirs(carpeta, exist_ok=True)
    fecha = HOY.strftime("%Y-%m-%d")

    archivos = {
        "senadores":          f"{carpeta}/senadores_{fecha}.csv",
        "reporte_provincial": f"{carpeta}/reporte_provincial_senado_{fecha}.csv",
        "reporte_partido":    f"{carpeta}/reporte_partido_senado_{fecha}.csv",
    }
    df_final.to_csv(archivos["senadores"],          index=False, encoding="utf-8-sig")
    df_prov.to_csv(archivos["reporte_provincial"],  index=False, encoding="utf-8-sig")
    df_partido.to_csv(archivos["reporte_partido"],  index=False, encoding="utf-8-sig")

    for nombre, ruta in archivos.items():
        size = os.path.getsize(ruta)
        print(f"💾 {nombre:25s} → {ruta}  ({size:,} bytes)")
