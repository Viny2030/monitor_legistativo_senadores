"""
test_api_senado.py
==================
Tests de integracion para api/run_senado.py usando FastAPI TestClient.
Mockea _latest_csv() para no depender de archivos en data/.

Cubre:
  - GET /         -> raiz con endpoints
  - GET /salud    -> status ok
  - GET /senado/senadores       -> lista de senadores (200 y csv_no_encontrado)
  - GET /senado/reporte-partido -> partidos (200 y csv_no_encontrado)
  - GET /senado/reporte-provincial -> provincias (200 y csv_no_encontrado)
"""
import sys
import os
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "")

import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# Importar la app DESPUES de setear vars de entorno
from api.run_senado import app

client = TestClient(app, raise_server_exceptions=False)


# --- CSV de prueba -----------------------------------------------------------

SENADORES_CSV = (
    "id,nombre,provincia,partido_normalizado,rol_provincial,"
    "votos_total,votos_afirmativos,votos_negativos,abstenciones,ausencias,"
    "participation_pct,foto,email\n"
    "1,GARCIA JUAN,Buenos Aires,UCR,Mayoria,10,8,1,1,0,90.0,,jg@senado.gob.ar\n"
    "2,LOPEZ MARIA,Cordoba,PRO,Primera Minoria,10,6,2,1,1,90.0,,lm@senado.gob.ar\n"
    "3,PEREZ CARLOS,Santa Fe,UxP,Mayoria,10,5,3,1,1,90.0,,pc@senado.gob.ar\n"
)

PARTIDO_CSV = (
    "partido,bancas\n"
    "UCR,30\n"
    "PRO,25\n"
    "UxP,17\n"
)

PROVINCIAL_CSV = (
    "provincia,senadores,participation_pct\n"
    "Buenos Aires,3,88.5\n"
    "Cordoba,3,75.0\n"
    "Santa Fe,3,82.0\n"
)


def _mock_csv(content: str):
    """Devuelve un Path falso cuyo .name es un nombre valido y pd.read_csv lo lee."""
    tmp = MagicMock(spec=Path)
    tmp.name = "senadores_2026-05-01.csv"
    # Hacer que pd.read_csv funcione con este mock via side_effect de open
    return tmp, content


# ============================================================================
# GET /
# ============================================================================

class TestRaiz:

    def test_retorna_200(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_tiene_proyecto(self):
        data = client.get("/").json()
        assert "proyecto" in data

    def test_tiene_endpoints(self):
        data = client.get("/").json()
        assert "endpoints" in data
        assert "senadores" in data["endpoints"]

    def test_version_presente(self):
        data = client.get("/").json()
        assert "version" in data


# ============================================================================
# GET /salud
# ============================================================================

class TestSalud:

    def test_retorna_200(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            resp = client.get("/salud")
        assert resp.status_code == 200

    def test_status_ok(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            data = client.get("/salud").json()
        assert data["status"] == "ok"

    def test_csv_none_cuando_no_hay_archivo(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            data = client.get("/salud").json()
        assert data["csv"] is None

    def test_csv_nombre_cuando_existe(self):
        mock_path = MagicMock(spec=Path)
        mock_path.name = "senadores_2026-05-01.csv"
        with patch("api.run_senado._latest_csv", return_value=mock_path):
            data = client.get("/salud").json()
        assert data["csv"] == "senadores_2026-05-01.csv"


# ============================================================================
# GET /senado/senadores
# ============================================================================

class TestSenadores:

    def test_sin_csv_retorna_ok_false(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            resp = client.get("/senado/senadores")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["senadores"] == []

    def test_con_csv_retorna_ok_true(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "senadores_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(SENADORES_CSV), encoding="utf-8")
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            resp = client.get("/senado/senadores")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_total_correcto(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "senadores_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(SENADORES_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            data = client.get("/senado/senadores").json()
        assert data["total"] == 3

    def test_estructura_senador(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "senadores_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(SENADORES_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            senadores = client.get("/senado/senadores").json()["senadores"]
        s = senadores[0]
        for campo in ("id", "nombre", "provincia", "partido",
                      "votos_total", "participation_pct"):
            assert campo in s

    def test_fuente_incluida(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "senadores_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(SENADORES_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            data = client.get("/senado/senadores").json()
        assert "fuente" in data


# ============================================================================
# GET /senado/reporte-partido
# ============================================================================

class TestReportePartido:

    def test_sin_csv_retorna_ok_false(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            resp = client.get("/senado/reporte-partido")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_con_csv_retorna_partidos(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "reporte_partido_senado_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(PARTIDO_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            data = client.get("/senado/reporte-partido").json()
        assert data["ok"] is True
        assert data["total"] == 3
        assert len(data["partidos"]) == 3

    def test_estructura_partido(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "reporte_partido_senado_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(PARTIDO_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            partidos = client.get("/senado/reporte-partido").json()["partidos"]
        assert "partido" in partidos[0]
        assert "bancas" in partidos[0]


# ============================================================================
# GET /senado/reporte-provincial
# ============================================================================

class TestReporteProvincial:

    def test_sin_csv_retorna_ok_false(self):
        with patch("api.run_senado._latest_csv", return_value=None):
            resp = client.get("/senado/reporte-provincial")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_con_csv_retorna_provincias(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "reporte_provincial_senado_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(PROVINCIAL_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            data = client.get("/senado/reporte-provincial").json()
        assert data["ok"] is True
        assert data["total"] == 3

    def test_estructura_provincia(self):
        mock_path = MagicMock(spec=Path)
        mock_path.__str__ = lambda self: "fake.csv"
        mock_path.name = "reporte_provincial_senado_2026-05-01.csv"
        df = pd.read_csv(io.StringIO(PROVINCIAL_CSV))
        with patch("api.run_senado._latest_csv", return_value=mock_path), \
             patch("pandas.read_csv", return_value=df):
            provincias = client.get("/senado/reporte-provincial").json()["provincias"]
        assert "provincia" in provincias[0]
        assert "senadores" in provincias[0]
