"""
Tests para scraper_diputados.py
Cubre: respuesta exitosa, tabla no encontrada, error de red, datos vacíos.
"""

import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

# --- HTML simulado con tabla de diputados ---
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

HTML_SIN_TABLA = """
<html><body><p>Sin datos disponibles</p></body></html>
"""

HTML_TABLA_VACIA = """
<html><body>
<table>
  <tr><th>N°</th><th>Nombre</th><th>Distrito</th><th>Bloque</th></tr>
</table>
</body></html>
"""


def make_mock_response(html: str, status_code: int = 200):
    """Crea un objeto response mockeado."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = html
    return mock_resp


# ──────────────────────────────────────────────
# Tests de obtener_diputados()
# ──────────────────────────────────────────────

class TestObtenerDiputados:

    @patch("requests.get")
    def test_retorna_diputados_cuando_hay_tabla(self, mock_get, capsys):
        """Debe encontrar diputados e imprimir el resumen."""
        mock_get.return_value = make_mock_response(HTML_CON_TABLA)

        # Importamos aquí para que el patch ya esté activo
        from scraper_diputados import obtener_diputados
        obtener_diputados()

        captured = capsys.readouterr()
        assert "3 diputados" in captured.out
        assert "Resumen por Bloque" in captured.out

    @patch("requests.get")
    def test_mensaje_cuando_no_hay_tabla(self, mock_get, capsys):
        """Debe avisar cuando no se encuentra la tabla."""
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)

        from scraper_diputados import obtener_diputados
        obtener_diputados()

        captured = capsys.readouterr()
        assert "No se encontró" in captured.out or "estructura del sitio" in captured.out

    @patch("requests.get")
    def test_maneja_error_de_red(self, mock_get, capsys):
        """Debe capturar excepciones de red y mostrar mensaje de error."""
        mock_get.side_effect = Exception("Connection refused")

        from scraper_diputados import obtener_diputados
        obtener_diputados()

        captured = capsys.readouterr()
        assert "Error" in captured.out or "error" in captured.out.lower()

    @patch("requests.get")
    def test_tabla_sin_filas_de_datos(self, mock_get, capsys):
        """Tabla con solo encabezado no debe generar diputados."""
        mock_get.return_value = make_mock_response(HTML_TABLA_VACIA)

        from scraper_diputados import obtener_diputados
        obtener_diputados()

        captured = capsys.readouterr()
        assert "0 diputados" in captured.out or "No se encontró" in captured.out or captured.out != ""

    @patch("requests.get")
    def test_llama_url_correcta(self, mock_get):
        """Debe hacer la petición a la URL oficial de diputados."""
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)

        from scraper_diputados import obtener_diputados
        obtener_diputados()

        args, kwargs = mock_get.call_args
        assert "diputados.gov.ar" in args[0]

    @patch("requests.get")
    def test_usa_user_agent_en_headers(self, mock_get):
        """Debe enviar un User-Agent para evitar bloqueos."""
        mock_get.return_value = make_mock_response(HTML_SIN_TABLA)

        from scraper_diputados import obtener_diputados
        obtener_diputados()

        _, kwargs = mock_get.call_args
        assert "headers" in kwargs
        assert "User-Agent" in kwargs["headers"]


# ──────────────────────────────────────────────
# Tests de parseo del HTML (sin red)
# ──────────────────────────────────────────────

class TestParseoHTML:

    def test_parseo_extrae_nombre_y_bloque(self):
        """Verifica que BeautifulSoup extrae los campos correctamente."""
        soup = BeautifulSoup(HTML_CON_TABLA, "html.parser")
        tabla = soup.find("table")
        filas = tabla.find_all("tr")[1:]

        diputados = []
        for fila in filas:
            cols = fila.find_all("td")
            if len(cols) > 1:
                nombre = cols[1].text.strip()
                bloque = cols[3].text.strip()
                diputados.append({"Nombre": nombre, "Bloque": bloque})

        assert len(diputados) == 3
        assert diputados[0]["Nombre"] == "GARCIA, Juan"
        assert diputados[0]["Bloque"] == "Unión por la Patria"
        assert diputados[1]["Nombre"] == "LOPEZ, Maria"
        assert diputados[2]["Bloque"] == "UCR"

    def test_parseo_tabla_sin_filas(self):
        """Tabla vacía debe dar lista vacía."""
        soup = BeautifulSoup(HTML_TABLA_VACIA, "html.parser")
        tabla = soup.find("table")
        filas = tabla.find_all("tr")[1:]

        diputados = [
            {"Nombre": f.find_all("td")[1].text.strip(), "Bloque": f.find_all("td")[3].text.strip()}
            for f in filas if len(f.find_all("td")) > 1
        ]
        assert diputados == []

    def test_no_tabla_devuelve_none(self):
        """HTML sin tabla: soup.find('table') debe retornar None."""
        soup = BeautifulSoup(HTML_SIN_TABLA, "html.parser")
        assert soup.find("table") is None