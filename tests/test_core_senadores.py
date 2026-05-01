"""
test_core_senadores.py
======================
Tests unitarios para core/senadores.py

Cubre:
  - calcular_kpis()       -> KPIs de participacion por senador
  - reporte_provincial()  -> agregacion por provincia
  - reporte_por_partido() -> bancas y roles por partido
  - resumen_camara()      -> metricas globales de la camara
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest
from core.senadores import (
    calcular_kpis,
    reporte_provincial,
    reporte_por_partido,
    resumen_camara,
    BANCAS_SENADO,
)


# --- helpers -----------------------------------------------------------------

def _nomina(n=3):
    rows = []
    provincias = ["Buenos Aires", "Cordoba", "Santa Fe", "Mendoza", "Salta"]
    partidos   = ["UCR", "PRO", "UxP"]
    for i in range(n):
        rows.append({
            "nombre":              f"SENADOR {i:02d}",
            "provincia":           provincias[i % len(provincias)],
            "partido_normalizado": partidos[i % len(partidos)],
            "rol_provincial":      None,
            "periodoLegal":        str({"inicio": "2023-12-10", "fin": "2029-12-10"}),
        })
    return pd.DataFrame(rows)


def _actas_con_votos(nomina_df):
    """Genera actas donde cada senador vota 'si' en todas las sesiones."""
    votos = [{"nombre": row["nombre"], "voto": "si"} for _, row in nomina_df.iterrows()]
    return pd.DataFrame([
        {"id": 1, "fecha": "2026-03-01", "votos": votos},
        {"id": 2, "fecha": "2026-03-15", "votos": votos},
    ])


# ============================================================================
# calcular_kpis
# ============================================================================

class TestCalcularKpis:

    def test_sin_actas_devuelve_kpis_en_cero(self):
        nomina = _nomina(4)
        df = calcular_kpis(nomina, pd.DataFrame())
        assert "votos_total" in df.columns
        assert df["votos_total"].sum() == 0
        assert df["participation_pct"].sum() == 0.0

    def test_sin_actas_conserva_filas_de_nomina(self):
        nomina = _nomina(6)
        df = calcular_kpis(nomina, pd.DataFrame())
        assert len(df) == 6

    def test_con_actas_calcula_votos_afirmativos(self):
        nomina = _nomina(3)
        actas  = _actas_con_votos(nomina)
        df = calcular_kpis(nomina, actas)
        # Cada senador voto 'si' en 2 sesiones
        assert df["votos_afirmativos"].min() == 2

    def test_participation_pct_entre_0_y_100(self):
        nomina = _nomina(3)
        actas  = _actas_con_votos(nomina)
        df = calcular_kpis(nomina, actas)
        assert (df["participation_pct"] >= 0).all()
        assert (df["participation_pct"] <= 100).all()

    def test_participation_pct_100_si_voto_siempre(self):
        nomina = _nomina(2)
        actas  = _actas_con_votos(nomina)
        df = calcular_kpis(nomina, actas)
        assert (df["participation_pct"] == 100.0).all()

    def test_participation_pct_50_si_voto_en_mitad(self):
        nomina = _nomina(1)
        senador = nomina.iloc[0]["nombre"]
        actas = pd.DataFrame([
            {"id": 1, "votos": [{"nombre": senador, "voto": "si"}]},
            {"id": 2, "votos": []},  # ausente
        ])
        df = calcular_kpis(nomina, actas)
        assert df.iloc[0]["participation_pct"] == 50.0

    def test_columnas_kpi_presentes(self):
        nomina = _nomina(3)
        df = calcular_kpis(nomina, pd.DataFrame())
        for col in ["votos_total", "votos_afirmativos", "votos_negativos",
                    "abstenciones", "ausencias", "participation_pct"]:
            assert col in df.columns

    def test_actas_sin_columna_votos_devuelve_ceros(self):
        nomina = _nomina(2)
        actas = pd.DataFrame([{"id": 1, "fecha": "2026-01-01"}])  # sin 'votos'
        df = calcular_kpis(nomina, actas)
        assert df["votos_total"].sum() == 0

    def test_votos_negativos_y_abstenciones_contados(self):
        nomina = pd.DataFrame([
            {"nombre": "A", "provincia": "BA", "partido_normalizado": "UCR",
             "rol_provincial": None, "periodoLegal": "{}"},
            {"nombre": "B", "provincia": "BA", "partido_normalizado": "PRO",
             "rol_provincial": None, "periodoLegal": "{}"},
        ])
        actas = pd.DataFrame([{
            "id": 1,
            "votos": [
                {"nombre": "A", "voto": "no"},
                {"nombre": "B", "voto": "abstencion"},
            ]
        }])
        df = calcular_kpis(nomina, actas)
        a = df[df["nombre"] == "A"].iloc[0]
        b = df[df["nombre"] == "B"].iloc[0]
        assert a["votos_negativos"] == 1
        assert b["abstenciones"] == 1


# ============================================================================
# reporte_provincial
# ============================================================================

class TestReporteProvincial:

    def _df_tres_provincias(self):
        return pd.DataFrame([
            {"nombre": "A", "provincia": "Buenos Aires",
             "partido_normalizado": "UCR", "participation_pct": 80.0},
            {"nombre": "B", "provincia": "Buenos Aires",
             "partido_normalizado": "PRO", "participation_pct": 70.0},
            {"nombre": "C", "provincia": "Buenos Aires",
             "partido_normalizado": "UCR", "participation_pct": 90.0},
            {"nombre": "D", "provincia": "Cordoba",
             "partido_normalizado": "UxP", "participation_pct": 60.0},
        ])

    def test_retorna_dataframe(self):
        df = reporte_provincial(self._df_tres_provincias())
        assert isinstance(df, pd.DataFrame)

    def test_columnas_requeridas(self):
        df = reporte_provincial(self._df_tres_provincias())
        assert "provincia" in df.columns
        assert "senadores" in df.columns

    def test_conteo_por_provincia(self):
        df = reporte_provincial(self._df_tres_provincias())
        ba = df[df["provincia"] == "Buenos Aires"]["senadores"].values[0]
        cb = df[df["provincia"] == "Cordoba"]["senadores"].values[0]
        assert ba == 3
        assert cb == 1

    def test_participation_pct_promedio(self):
        df = reporte_provincial(self._df_tres_provincias())
        ba = df[df["provincia"] == "Buenos Aires"]["participation_pct"].values[0]
        esperado = round((80.0 + 70.0 + 90.0) / 3, 1)
        assert ba == esperado

    def test_una_provincia_por_fila(self):
        df = reporte_provincial(self._df_tres_provincias())
        assert df["provincia"].nunique() == len(df)

    def test_df_vacio_retorna_df_vacio(self):
        df = reporte_provincial(pd.DataFrame(columns=["nombre", "provincia",
                                                       "partido_normalizado"]))
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ============================================================================
# reporte_por_partido
# ============================================================================

class TestReportePorPartido:

    def _df(self):
        return pd.DataFrame([
            {"nombre": "A", "partido_normalizado": "UCR",
             "rol_provincial": "Mayoria"},
            {"nombre": "B", "partido_normalizado": "UCR",
             "rol_provincial": "Mayoria"},
            {"nombre": "C", "partido_normalizado": "PRO",
             "rol_provincial": "Primera Minoria"},
            {"nombre": "D", "partido_normalizado": "UxP",
             "rol_provincial": "Primera Minoria"},
        ])

    def test_retorna_dataframe(self):
        df = reporte_por_partido(self._df())
        assert isinstance(df, pd.DataFrame)

    def test_columnas_requeridas(self):
        df = reporte_por_partido(self._df())
        assert "partido" in df.columns
        assert "bancas" in df.columns

    def test_bancas_ucr_correctas(self):
        df = reporte_por_partido(self._df())
        ucr = df[df["partido"] == "UCR"]["bancas"].values[0]
        assert ucr == 2

    def test_ordenado_por_bancas_descendente(self):
        df = reporte_por_partido(self._df())
        bancas = df["bancas"].tolist()
        assert bancas == sorted(bancas, reverse=True)

    def test_tres_partidos_en_resultado(self):
        df = reporte_por_partido(self._df())
        assert len(df) == 3

    def test_suma_total_bancas(self):
        df = reporte_por_partido(self._df())
        assert df["bancas"].sum() == 4


# ============================================================================
# resumen_camara
# ============================================================================

class TestResumenCamara:

    def _df_nomina(self):
        return pd.DataFrame([
            {"nombre": "A", "provincia": "BA",
             "partido_normalizado": "UCR", "rol_provincial": "Mayoria",
             "participation_pct": 80.0,
             "periodoLegal": str({"inicio": "2023-12-10", "fin": "2029-12-10"})},
            {"nombre": "B", "provincia": "Cordoba",
             "partido_normalizado": "PRO", "rol_provincial": "Primera Minoria",
             "participation_pct": 70.0,
             "periodoLegal": str({"inicio": "2023-12-10", "fin": "2027-12-10"})},
            {"nombre": "C", "provincia": "Santa Fe",
             "partido_normalizado": "UCR", "rol_provincial": "Mayoria",
             "participation_pct": 90.0,
             "periodoLegal": str({"inicio": "2021-12-10", "fin": "2027-12-10"})},
        ])

    def _df_partido(self):
        return pd.DataFrame([
            {"partido": "UCR", "bancas": 2},
            {"partido": "PRO", "bancas": 1},
        ])

    def test_retorna_dict(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert isinstance(resultado, dict)

    def test_campos_requeridos(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        for campo in ("total_senadores", "esperado", "completo",
                      "provincias", "partido_lider", "bancas_lider",
                      "participation_pct_avg", "fecha_actualizacion"):
            assert campo in resultado

    def test_total_senadores_correcto(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["total_senadores"] == 3

    def test_esperado_es_72(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["esperado"] == BANCAS_SENADO

    def test_completo_false_con_menos_de_72(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["completo"] is False

    def test_partido_lider_es_ucr(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["partido_lider"] == "UCR"

    def test_bancas_lider_es_2(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["bancas_lider"] == 2

    def test_participation_pct_avg_calculado(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        esperado = round((80.0 + 70.0 + 90.0) / 3, 1)
        assert resultado["participation_pct_avg"] == esperado

    def test_provincias_distintas(self):
        resultado = resumen_camara(self._df_nomina(), self._df_partido())
        assert resultado["provincias"] == 3
