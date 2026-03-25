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

        # Participation Index (0–100)
        max_v = df_result["total_votos"].max()
        if max_v and max_v > 0:
            df_result["participation_index"] = (df_result["total_votos"] / max_v * 100).round(1)
    else:
        df_result = df_nomina.copy()

    print(f"✅ KPIs listos para {len(df_result)} senadores")
    return df_result


# ── 4a. Reporte por Provincia ─────────────────────────────────────────────────
def reporte_provincial(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa por provincia — eje federal del Senado (3 senadores por provincia)."""
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
    """Agrupa por partido político — eje de bloques del Senado."""
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
