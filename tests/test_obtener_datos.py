"""
Tests para obtener_datos.py
Cubre: extracción exitosa + guardado CSV, tabla ausente, error de red,
       contenido del CSV generado y columnas del DataFrame.
"""

import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

# --- HTML simulado ---
HTML_CON_TABLA = """
<html><body>
<table>
  <tr><th>N°</th><th>Nombre</th><th>Distrito</th><th>Bloque</th></tr>
  <tr><td>1</td><td>GARCIA, Juan</td><td>Buenos Aires</td><td>Unión por la Patria</td></tr>
  <tr><td>2</td><td>LOPEZ, Maria</td><td>Córdoba</td><td>PRO</td></tr>
  <tr><td>3</td><td>PEREZ, Carlos</td><td>Santa Fe</td><td>UCR</td></tr>
</table>
</body></html>
"""

HTML_SIN_TABLA = """<html><body><p>Sin datos</p></body></html>"""

CSV_SALIDA = "nomina_diputados.csv"


def make_mock_response(html: str):
    mock_resp = MagicMock()
    mock_resp.text = html
    return mock_resp


# ──────────────────────────────────────────────
# Tests de extraer_diputados()
# ──────────────────────────────────────────────

class TestExtraerDiputados:

    @patch("requests.get")
    def test_crea_csv_cuando_hay_datos(self, mock_get, tmp_path, monkeypatch, capsys):
        """Debe crear el archivo CSV con los datos parseados."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        # Redirigir el CSV al directorio temporal
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        assert (tmp_path / CSV_SALIDA).exists()
        captured = capsys.readouterr()
        assert "Éxito" in captured.out or "éxito" in captured.out.lower()

    @patch("requests.get")
    def test_csv_tiene_columnas_correctas(self, mock_get, tmp_path, monkeypatch):
        """El CSV generado debe tener columnas Nombre, Distrito, Bloque."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        df = pd.read_csv(tmp_path / CSV_SALIDA)
        assert "Nombre" in df.columns
        assert "Distrito" in df.columns
        assert "Bloque" in df.columns

    @patch("requests.get")
    def test_csv_tiene_tres_filas(self, mock_get, tmp_path, monkeypatch):
        """El CSV debe tener una fila por cada diputado del HTML mockeado."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        df = pd.read_csv(tmp_path / CSV_SALIDA)
        assert len(df) == 3

    @patch("requests.get")
    def test_csv_contiene_datos_correctos(self, mock_get, tmp_path, monkeypatch):
        """Los valores del CSV deben coincidir con el HTML simulado."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        df = pd.read_csv(tmp_path / CSV_SALIDA)
        assert df.iloc[0]["Nombre"] == "GARCIA, Juan"
        assert df.iloc[0]["Distrito"] == "Buenos Aires"
        assert df.iloc[0]["Bloque"] == "Unión por la Patria"
        assert df.iloc[1]["Nombre"] == "LOPEZ, Maria"

    @patch("requests.get")
    def test_avisa_cuando_no_hay_tabla(self, mock_get, capsys):
        """Sin tabla debe imprimir una advertencia, sin crear CSV ni lanzar excepción."""
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)

        from obtener_datos import extraer_diputados
        extraer_diputados()  # No debe lanzar excepción

        captured = capsys.readouterr()
        assert "No se encontró" in captured.out or "⚠️" in captured.out

    @patch("requests.get")
    def test_maneja_excepcion_de_red(self, mock_get, capsys):
        """Ante un error de conexión debe capturar y mostrar mensaje."""
        mock_get.side_effect = ConnectionError("Timeout")

        from obtener_datos import extraer_diputados
        extraer_diputados()  # No debe propagar la excepción

        captured = capsys.readouterr()
        assert "Error" in captured.out or "❌" in captured.out

    @patch("requests.get")
    def test_url_apunta_a_diputados_gov(self, mock_get):
        """La URL utilizada debe ser la del sitio oficial."""
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        args, kwargs = mock_get.call_args
        assert "diputados.gov.ar" in args[0]

    @patch("requests.get")
    def test_encoding_utf8_en_csv(self, mock_get, tmp_path, monkeypatch):
        """El CSV debe guardarse con encoding UTF-8 para preservar tildes."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        # Leer con UTF-8 no debe lanzar error de decodificación
        df = pd.read_csv(tmp_path / CSV_SALIDA, encoding="utf-8")
        assert "Unión por la Patria" in df["Bloque"].values

    @patch("requests.get")
    def test_imprime_cantidad_de_diputados(self, mock_get, tmp_path, monkeypatch, capsys):
        """Debe imprimir la cantidad de registros encontrados."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)
        monkeypatch.chdir(tmp_path)

        from obtener_datos import extraer_diputados
        extraer_diputados()

        captured = capsys.readouterr()
        assert "3" in captured.out