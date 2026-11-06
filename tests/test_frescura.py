"""frescura.py — formato común de la ficha de frescura (sin red)."""
from datetime import date

from frescura import evaluar, fecha_es

HOY = date(2026, 11, 6)


def test_fecha_es_formatos():
    assert fecha_es("04 Noviembre 2026") == date(2026, 11, 4)
    assert fecha_es("4 de noviembre de 2026") == date(2026, 11, 4)
    assert fecha_es("Enero 2026") == date(2026, 1, 31)
    assert fecha_es("Diciembre 2025") == date(2025, 12, 31)
    assert fecha_es("Período 144 01/03/2026 al 09/09/2026".split(" al ")[-1]) == date(2026, 9, 9)
    assert fecha_es("2026-10-07") == date(2026, 10, 7)
    assert fecha_es("sin fecha") is None and fecha_es(None) is None


def test_estados_tecnico_contenido_y_al_dia():
    r = evaluar("x", [
        {"id": "ok", "ultima_carga": "2026-11-06T09:30:00", "max_dias_carga": 3,
         "periodo_fin": "2026-11-04", "max_dias_periodo": 45},
        {"id": "pipeline_caido", "ultima_carga": "2026-10-20T09:30:00", "max_dias_carga": 3,
         "periodo_fin": "2026-11-04", "max_dias_periodo": 45},
        {"id": "fuente_sin_publicar", "ultima_carga": "2026-11-06", "max_dias_carga": 3,
         "periodo_fin": "Enero 2026", "max_dias_periodo": 60},
        {"id": "manual", "ultima_carga": None, "periodo_fin": "2025-12-31", "max_dias_periodo": 545},
    ], hoy=HOY)
    estados = {d["id"]: d["estado"] for d in r["datos"]}
    assert estados == {"ok": "al_dia", "pipeline_caido": "atrasado_tecnico",
                       "fuente_sin_publicar": "atrasado_contenido", "manual": "al_dia"}
    assert r["resumen"] == {"al_dia": 2, "atrasado_tecnico": 1, "atrasado_contenido": 1}
    assert r["formato"] == "frescura/1"
    sin = next(d for d in r["datos"] if d["id"] == "fuente_sin_publicar")
    assert sin["periodo_fin"] == "2026-01-31" and sin["dias_desde_periodo"] == 279


def test_el_tecnico_tiene_prioridad_y_sin_fecha_de_carga_es_tecnico():
    r = evaluar("x", [{"id": "a", "ultima_carga": None, "max_dias_carga": 3,
                       "periodo_fin": "2020-01-01", "max_dias_periodo": 10}], hoy=HOY)
    assert r["datos"][0]["estado"] == "atrasado_tecnico"


def test_endpoint_frescura():
    from fastapi.testclient import TestClient
    import api.run_senado as rs
    r = TestClient(rs.app).get("/api/frescura")
    assert r.status_code == 200
    d = r.json()
    assert d["sitio"] == "senadores" and d["formato"] == "frescura/1"
    ids = {x["id"] for x in d["datos"]}
    assert {"nomina", "dieta", "presupuesto", "versiones_taquigraficas"} <= ids
    assert all(x["estado"] in ("al_dia", "atrasado_tecnico", "atrasado_contenido") for x in d["datos"])
