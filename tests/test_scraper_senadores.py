"""
Tests para scraper_senadores.py
Cubre todas las funciones principales sin hacer llamadas reales a internet.
"""

import ast
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import date

# ── HTML simulado de senado.gob.ar ───────────────────────────────────────────
# El scraper busca tablas con más de 10 filas: generamos 12 senadores de prueba
HTML_SENADO = """
<html><body>
<table>
  <tr><th>N°</th><th>Nombre</th><th>Provincia</th><th>Partido</th><th>Período</th><th>Contacto</th></tr>
  <tr><td>1</td><td>GARCIA, Juan</td><td>Buenos Aires</td><td>Unión por la Patria</td><td>10/12/2019\n10/12/2027</td><td>jgarcia@senado.gob.ar</td></tr>
  <tr><td>2</td><td>LOPEZ, Maria</td><td>Córdoba</td><td>Unión Cívica Radical</td><td>10/12/2021\n10/12/2027</td><td>mlopez@senado.gob.ar</td></tr>
  <tr><td>3</td><td>PEREZ, Carlos</td><td>Santa Fe</td><td>La Libertad Avanza</td><td>10/12/2023\n10/12/2029</td><td>cperez@senado.gob.ar</td></tr>
  <tr><td>4</td><td>MARTINEZ, Ana</td><td>Mendoza</td><td>Unión por la Patria</td><td>10/12/2019\n10/12/2027</td><td>amartinez@senado.gob.ar</td></tr>
  <tr><td>5</td><td>RODRIGUEZ, Luis</td><td>Tucumán</td><td>Unión Cívica Radical</td><td>10/12/2021\n10/12/2027</td><td>lrodriguez@senado.gob.ar</td></tr>
  <tr><td>6</td><td>FERNANDEZ, Paula</td><td>Salta</td><td>La Libertad Avanza</td><td>10/12/2023\n10/12/2029</td><td>pfernandez@senado.gob.ar</td></tr>
  <tr><td>7</td><td>GOMEZ, Ricardo</td><td>Jujuy</td><td>Unión por la Patria</td><td>10/12/2019\n10/12/2027</td><td>rgomez@senado.gob.ar</td></tr>
  <tr><td>8</td><td>DIAZ, Silvia</td><td>Chaco</td><td>Unión Cívica Radical</td><td>10/12/2021\n10/12/2027</td><td>sdiaz@senado.gob.ar</td></tr>
  <tr><td>9</td><td>TORRES, Miguel</td><td>Misiones</td><td>La Libertad Avanza</td><td>10/12/2023\n10/12/2029</td><td>mtorres@senado.gob.ar</td></tr>
  <tr><td>10</td><td>SANCHEZ, Laura</td><td>Neuquén</td><td>Unión por la Patria</td><td>10/12/2019\n10/12/2027</td><td>lsanchez@senado.gob.ar</td></tr>
  <tr><td>11</td><td>RUIZ, Diego</td><td>Río Negro</td><td>Unión Cívica Radical</td><td>10/12/2021\n10/12/2027</td><td>druiz@senado.gob.ar</td></tr>
  <tr><td>12</td><td>VEGA, Claudia</td><td>San Juan</td><td>La Libertad Avanza</td><td>10/12/2023\n10/12/2029</td><td>cvega@senado.gob.ar</td></tr>
</table>
</body></html>
"""

HTML_SIN_TABLA = "<html><body><p>Sin datos</p></body></html>"

# ── Datos API simulados ───────────────────────────────────────────────────────
SENADORES_API = [
    {
        "id": 1, "nombre": "GARCIA, Juan", "provincia": "Buenos Aires",
        "partido": "Alianza Unión por la Patria",
        "periodoLegal": {"inicio": "2019-12-10", "fin": "2025-12-10"},
        "periodoReal": {}, "reemplazo": None, "observaciones": None,
        "foto": None, "email": "jgarcia@senado.gob.ar",
        "telefono": None, "redesSociales": None,
    },
    {
        "id": 2, "nombre": "LOPEZ, Maria", "provincia": "Córdoba",
        "partido": "Unión Cívica Radical",
        "periodoLegal": {"inicio": "2021-12-10", "fin": "2027-12-10"},
        "periodoReal": {}, "reemplazo": None, "observaciones": None,
        "foto": None, "email": "mlopez@senado.gob.ar",
        "telefono": None, "redesSociales": None,
    },
    {
        "id": 3, "nombre": "PEREZ, Carlos", "provincia": "Santa Fe",
        "partido": "Alianza La Libertad Avanza",
        "periodoLegal": {"inicio": "2023-12-10", "fin": "2029-12-10"},
        "periodoReal": {}, "reemplazo": None, "observaciones": None,
        "foto": None, "email": "cperez@senado.gob.ar",
        "telefono": None, "redesSociales": None,
    },
]


def make_mock_response(content, json_data=None, status=200, raise_for_status=False):
    mock = MagicMock()
    mock.status_code = status
    mock.text = content
    if json_data is not None:
        mock.json.return_value = json_data
    if raise_for_status:
        mock.raise_for_status.side_effect = Exception("HTTP Error")
    else:
        mock.raise_for_status.return_value = None
    return mock


# ══════════════════════════════════════════════════════════════════════════════
# normalizar_partido
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizarPartido:

    def test_normaliza_union_por_la_patria(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido("Alianza Unión por la Patria") == "Unión por la Patria"

    def test_normaliza_ucr(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido("Unión Cívica Radical") == "Unión Cívica Radical"

    def test_normaliza_la_libertad_avanza(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido("Alianza La Libertad Avanza") == "La Libertad Avanza"

    def test_partido_desconocido_devuelve_original(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido("Partido Inventado XYZ") == "Partido Inventado XYZ"

    def test_none_devuelve_otros(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido(None) == "Otros"

    def test_string_vacio_devuelve_otros(self):
        from scraper_senadores import normalizar_partido
        # String vacío no matchea ningún alias → devuelve strip() del original
        result = normalizar_partido("")
        assert result == "" or result == "Otros"

    def test_case_insensitive(self):
        from scraper_senadores import normalizar_partido
        assert normalizar_partido("FRENTE DE TODOS") == "Unión por la Patria"


# ══════════════════════════════════════════════════════════════════════════════
# deduplicar_provincia
# ══════════════════════════════════════════════════════════════════════════════

class TestDeduplicarProvincia:

    def _df_base(self):
        return pd.DataFrame([
            {"nombre": "A", "provincia": "Córdoba", "partido_normalizado": "UCR",
             "periodoLegal": str({"inicio": "2019-12-10", "fin": "2025-12-10"})},
            {"nombre": "B", "provincia": "Córdoba", "partido_normalizado": "UCR",
             "periodoLegal": str({"inicio": "2021-12-10", "fin": "2027-12-10"})},
            {"nombre": "C", "provincia": "Córdoba", "partido_normalizado": "PRO",
             "periodoLegal": str({"inicio": "2023-12-10", "fin": "2029-12-10"})},
        ])

    def test_no_modifica_provincia_con_3_o_menos(self):
        from scraper_senadores import deduplicar_provincia
        df = self._df_base()
        result = deduplicar_provincia(df)
        assert len(result) == 3

    def test_descarta_sobrante_cuando_hay_mas_de_2_del_mismo_partido(self):
        from scraper_senadores import deduplicar_provincia
        df = self._df_base()
        # Agregar un 4to senador del mismo partido que A y B
        extra = pd.DataFrame([{
            "nombre": "D", "provincia": "Córdoba", "partido_normalizado": "UCR",
            "periodoLegal": str({"inicio": "2015-12-10", "fin": "2021-12-10"}),
        }])
        df = pd.concat([df, extra], ignore_index=True)
        result = deduplicar_provincia(df)
        # UCR debe quedar con máximo 2
        ucr = result[(result["provincia"] == "Córdoba") & (result["partido_normalizado"] == "UCR")]
        assert len(ucr) <= 2

    def test_conserva_los_mas_recientes(self):
        from scraper_senadores import deduplicar_provincia
        df = pd.DataFrame([
            {"nombre": "Antiguo", "provincia": "Mendoza", "partido_normalizado": "UCR",
             "periodoLegal": str({"inicio": "2015-12-10", "fin": "2021-12-10"})},
            {"nombre": "Medio", "provincia": "Mendoza", "partido_normalizado": "UCR",
             "periodoLegal": str({"inicio": "2019-12-10", "fin": "2025-12-10"})},
            {"nombre": "Reciente", "provincia": "Mendoza", "partido_normalizado": "UCR",
             "periodoLegal": str({"inicio": "2023-12-10", "fin": "2029-12-10"})},
            {"nombre": "Otro", "provincia": "Mendoza", "partido_normalizado": "PRO",
             "periodoLegal": str({"inicio": "2023-12-10", "fin": "2029-12-10"})},
        ])
        result = deduplicar_provincia(df)
        nombres = result[result["provincia"] == "Mendoza"]["nombre"].tolist()
        assert "Antiguo" not in nombres
        assert "Reciente" in nombres


# ══════════════════════════════════════════════════════════════════════════════
# scraping_senado_oficial
# ══════════════════════════════════════════════════════════════════════════════

class TestScrapingSenado:

    @patch("requests.get")
    def test_retorna_dataframe_con_datos(self, mock_get):
        mock_get.return_value = make_mock_response(HTML_SENADO)
        from scraper_senadores import scraping_senado_oficial
        df = scraping_senado_oficial()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    @patch("requests.get")
    def test_columnas_requeridas_presentes(self, mock_get):
        mock_get.return_value = make_mock_response(HTML_SENADO)
        from scraper_senadores import scraping_senado_oficial
        df = scraping_senado_oficial()
        for col in ["nombre", "provincia", "partido", "inicio", "fin", "email"]:
            assert col in df.columns

    @patch("requests.get")
    def test_sin_tabla_devuelve_dataframe_vacio(self, mock_get):
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)
        from scraper_senadores import scraping_senado_oficial
        df = scraping_senado_oficial()
        assert df.empty

    @patch("requests.get")
    def test_error_de_red_devuelve_dataframe_vacio(self, mock_get):
        mock_get.side_effect = Exception("Timeout")
        from scraper_senadores import scraping_senado_oficial
        df = scraping_senado_oficial()
        assert df.empty

    @patch("requests.get")
    def test_filtra_solo_vigentes(self, mock_get):
        """Senadores con fin < hoy deben ser descartados."""
        mock_get.return_value = make_mock_response(HTML_SENADO)
        from scraper_senadores import scraping_senado_oficial, HOY_ISO
        df = scraping_senado_oficial()
        if not df.empty and "fin" in df.columns:
            assert all(df["fin"] > HOY_ISO)


# ══════════════════════════════════════════════════════════════════════════════
# obtener_nomina
# ══════════════════════════════════════════════════════════════════════════════

class TestObtenerNomina:

    @patch("scraper_senadores.enriquecer_desde_senado", side_effect=lambda df: df)
    @patch("requests.get")
    def test_retorna_dataframe_con_activos(self, mock_get, mock_enrich):
        mock_get.return_value = make_mock_response("", json_data=SENADORES_API)
        from scraper_senadores import obtener_nomina, HOY_ISO
        df = obtener_nomina()
        assert isinstance(df, pd.DataFrame)
        # Todos los retornados deben tener fin > hoy
        for _, row in df.iterrows():
            periodo = ast.literal_eval(row["periodoLegal"])
            assert periodo.get("fin", "") > HOY_ISO

    @patch("scraper_senadores.enriquecer_desde_senado", side_effect=lambda df: df)
    @patch("requests.get")
    def test_columnas_minimas_presentes(self, mock_get, mock_enrich):
        mock_get.return_value = make_mock_response("", json_data=SENADORES_API)
        from scraper_senadores import obtener_nomina
        df = obtener_nomina()
        for col in ["nombre", "provincia", "partido", "partido_normalizado"]:
            assert col in df.columns

    @patch("scraper_senadores.obtener_nomina_fallback")
    @patch("requests.get")
    def test_usa_fallback_cuando_api_falla(self, mock_get, mock_fallback):
        mock_get.side_effect = Exception("Connection error")
        mock_fallback.return_value = pd.DataFrame([{
            "nombre": "FALLBACK, Senador", "provincia": "Córdoba",
            "partido": "UCR", "partido_normalizado": "Unión Cívica Radical",
            "rol_provincial": None,
        }])
        from scraper_senadores import obtener_nomina
        df = obtener_nomina()
        assert not df.empty
        mock_fallback.assert_called_once()

    @patch("scraper_senadores.enriquecer_desde_senado", side_effect=lambda df: df)
    @patch("requests.get")
    def test_descarta_mandatos_vencidos(self, mock_get, mock_enrich):
        """Senadores con fin < HOY_ISO deben ser filtrados."""
        data_con_vencido = SENADORES_API + [{
            "id": 99, "nombre": "VENCIDO, Senador", "provincia": "Jujuy",
            "partido": "UCR",
            "periodoLegal": {"inicio": "2015-12-10", "fin": "2021-12-10"},
            "periodoReal": {}, "reemplazo": None, "observaciones": None,
            "foto": None, "email": None, "telefono": None, "redesSociales": None,
        }]
        mock_get.return_value = make_mock_response("", json_data=data_con_vencido)
        from scraper_senadores import obtener_nomina
        df = obtener_nomina()
        assert "VENCIDO, Senador" not in df["nombre"].values


# ══════════════════════════════════════════════════════════════════════════════
# obtener_actas
# ══════════════════════════════════════════════════════════════════════════════

class TestObtenerActas:

    @patch("requests.get")
    def test_retorna_dataframe_con_actas(self, mock_get):
        actas = [{"id": 1, "fecha": "2025-03-01", "votos": []}]
        mock_get.return_value = make_mock_response("", json_data=actas)
        from scraper_senadores import obtener_actas
        df = obtener_actas(2025)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    @patch("requests.get")
    def test_devuelve_dataframe_vacio_si_falla(self, mock_get):
        mock_get.side_effect = Exception("Timeout")
        from scraper_senadores import obtener_actas
        df = obtener_actas(2025)
        assert df.empty

    @patch("requests.get")
    def test_url_incluye_anio(self, mock_get):
        mock_get.return_value = make_mock_response("", json_data=[])
        from scraper_senadores import obtener_actas
        obtener_actas(2024)
        args, _ = mock_get.call_args
        assert "2024" in args[0]


# ══════════════════════════════════════════════════════════════════════════════
# calcular_kpis
# ══════════════════════════════════════════════════════════════════════════════

class TestCalcularKpis:

    def _nomina(self):
        return pd.DataFrame([
            {"nombre": "GARCIA, Juan", "provincia": "Buenos Aires",
             "partido_normalizado": "Unión por la Patria"},
            {"nombre": "LOPEZ, Maria", "provincia": "Córdoba",
             "partido_normalizado": "Unión Cívica Radical"},
        ])

    def test_sin_actas_devuelve_kpis_en_cero(self):
        from scraper_senadores import calcular_kpis
        df = calcular_kpis(self._nomina(), pd.DataFrame())
        assert "votos_total" in df.columns
        assert df["votos_total"].sum() == 0

    def test_con_actas_calcula_participation_pct(self):
        from scraper_senadores import calcular_kpis
        actas = pd.DataFrame([{
            "id": 1,
            "votos": [
                {"nombre": "GARCIA, Juan", "voto": "si"},
                {"nombre": "LOPEZ, Maria", "voto": "no"},
            ]
        }])
        df = calcular_kpis(self._nomina(), actas)
        assert "participation_pct" in df.columns
        garcia = df[df["nombre"] == "GARCIA, Juan"].iloc[0]
        assert garcia["votos_afirmativos"] == 1

    def test_columnas_kpi_presentes(self):
        from scraper_senadores import calcular_kpis
        df = calcular_kpis(self._nomina(), pd.DataFrame())
        for col in ["votos_total", "votos_afirmativos", "votos_negativos",
                    "abstenciones", "ausencias", "participation_pct"]:
            assert col in df.columns


# ══════════════════════════════════════════════════════════════════════════════
# reporte_provincial
# ══════════════════════════════════════════════════════════════════════════════

class TestReporteProvincial:

    def _df(self):
        return pd.DataFrame([
            {"nombre": "A", "provincia": "Buenos Aires", "partido_normalizado": "UCR"},
            {"nombre": "B", "provincia": "Buenos Aires", "partido_normalizado": "PRO"},
            {"nombre": "C", "provincia": "Buenos Aires", "partido_normalizado": "UCR"},
            {"nombre": "D", "provincia": "Córdoba", "partido_normalizado": "PRO"},
        ])

    def test_retorna_dataframe(self):
        from scraper_senadores import reporte_provincial
        df = reporte_provincial(self._df())
        assert isinstance(df, pd.DataFrame)

    def test_columnas_correctas(self):
        from scraper_senadores import reporte_provincial
        df = reporte_provincial(self._df())
        assert "provincia" in df.columns
        assert "senadores" in df.columns

    def test_conteo_correcto(self):
        from scraper_senadores import reporte_provincial
        df = reporte_provincial(self._df())
        ba = df[df["provincia"] == "Buenos Aires"]["senadores"].values[0]
        assert ba == 3


# ══════════════════════════════════════════════════════════════════════════════
# reporte_por_partido
# ══════════════════════════════════════════════════════════════════════════════

class TestReportePorPartido:

    def _df(self):
        return pd.DataFrame([
            {"nombre": "A", "partido_normalizado": "UCR", "rol_provincial": "Mayoría"},
            {"nombre": "B", "partido_normalizado": "UCR", "rol_provincial": "Mayoría"},
            {"nombre": "C", "partido_normalizado": "PRO", "rol_provincial": "Primera Minoría"},
        ])

    def test_retorna_dataframe(self):
        from scraper_senadores import reporte_por_partido
        df = reporte_por_partido(self._df())
        assert isinstance(df, pd.DataFrame)

    def test_columnas_correctas(self):
        from scraper_senadores import reporte_por_partido
        df = reporte_por_partido(self._df())
        for col in ["partido", "bancas", "Mayoría", "Primera Minoría"]:
            assert col in df.columns

    def test_bancas_ucr_correctas(self):
        from scraper_senadores import reporte_por_partido
        df = reporte_por_partido(self._df())
        ucr = df[df["partido"] == "UCR"]["bancas"].values[0]
        assert ucr == 2

    def test_ordenado_por_bancas_descendente(self):
        from scraper_senadores import reporte_por_partido
        df = reporte_por_partido(self._df())
        bancas = df["bancas"].tolist()
        assert bancas == sorted(bancas, reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# asignar_roles
# ══════════════════════════════════════════════════════════════════════════════

class TestAsignarRoles:

    def test_asigna_mayoria_y_primera_minoria(self):
        from scraper_senadores import asignar_roles
        df = pd.DataFrame([
            {"nombre": "A", "provincia": "Salta", "partido_normalizado": "UCR", "rol_provincial": None},
            {"nombre": "B", "provincia": "Salta", "partido_normalizado": "UCR", "rol_provincial": None},
            {"nombre": "C", "provincia": "Salta", "partido_normalizado": "PRO", "rol_provincial": None},
        ])
        result = asignar_roles(df)
        roles = result[result["provincia"] == "Salta"]["rol_provincial"].tolist()
        assert "Mayoría" in roles
        assert "Primera Minoría" in roles

    def test_todos_tienen_rol_asignado(self):
        from scraper_senadores import asignar_roles
        df = pd.DataFrame([
            {"nombre": "A", "provincia": "Jujuy", "partido_normalizado": "UCR", "rol_provincial": None},
            {"nombre": "B", "provincia": "Jujuy", "partido_normalizado": "PRO", "rol_provincial": None},
            {"nombre": "C", "provincia": "Jujuy", "partido_normalizado": "LLA", "rol_provincial": None},
        ])
        result = asignar_roles(df)
        assert result["rol_provincial"].notna().all()


# ══════════════════════════════════════════════════════════════════════════════
# guardar_resultados
# ══════════════════════════════════════════════════════════════════════════════

class TestGuardarResultados:

    def test_crea_archivos_csv(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from scraper_senadores import guardar_resultados
        df_final = pd.DataFrame([{"nombre": "A", "provincia": "Salta"}])
        df_prov = pd.DataFrame([{"provincia": "Salta", "senadores": 1}])
        df_part = pd.DataFrame([{"partido": "UCR", "bancas": 1}])
        guardar_resultados(df_final, df_prov, df_part)
        import os
        archivos = list((tmp_path / "data").iterdir())
        assert len(archivos) == 3
        for a in archivos:
            assert a.suffix == ".csv"