"""Red de coincidencia de votos (red_votos.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import red_votos as rv  # noqa: E402


def _votaciones(n=25):
    # A y B votan siempre igual; C vota igual que A salvo en 5; D siempre al revés de A.
    out = []
    for i in range(n):
        a = "si" if i % 2 else "no"
        c = a if i >= 5 else ("no" if a == "si" else "si")
        d = "no" if a == "si" else "si"
        out.append({"Pérez, Ana": a, "Gómez, Bruno": a, "Ríos, Carla": c, "Díaz, Dario": d,
                    "Sosa, Eva": "ausente"})
    return out


BLOQUES = {"PEREZ ANA": "Azul", "GOMEZ BRUNO": "Azul", "RIOS CARLA": "Rojo", "DIAZ DARIO": "Rojo"}


def test_normalizar_y_codigos():
    assert rv.normalizar_nombre("Ríos, Carla María") == "RIOS CARLA MARIA"
    assert rv.codigo_voto("Afirmativo") == rv.codigo_voto("si") == 1
    assert rv.codigo_voto("negativo") == 2 and rv.codigo_voto("abstención") == 3
    assert rv.codigo_voto("ausente") == 0 and rv.codigo_voto("presidente") == 0


def test_coincidencias_y_aristas():
    red = rv.construir_red(_votaciones(), BLOQUES, k=1)
    por = {n["id"]: n for n in red["nodos"]}
    # Sosa nunca votó: queda sin coincidencias y fuera de la nómina actual
    assert por["Sosa, Eva"]["bloque"] == rv.SIN_BLOQUE and por["Sosa, Eva"]["votos"] == 0
    a = next(x for x in red["aristas"] if {x["from"], x["to"]} == {"Pérez, Ana", "Gómez, Bruno"})
    assert a["coincidencia"] == 100.0 and not a["entre_bloques"]
    c = next(x for x in red["aristas"] if "Ríos, Carla" in (x["from"], x["to"]) and x["entre_bloques"])
    assert c["entre_bloques"] and c["coincidencia"] == 80.0  # 20 de 25
    assert por["Ríos, Carla"]["mas_cercano_otro_bloque"]["coincidencia"] == 80.0
    assert por["Díaz, Dario"]["coincidencia_otros"] < 25


def test_minimo_de_votaciones_en_comun():
    red = rv.construir_red(_votaciones(10), BLOQUES, k=3, min_comunes=20)
    assert red["aristas"] == []


def test_bloque_por_apellido_y_primer_nombre():
    assert rv.buscar_bloque("Ríos, Carla Beatriz", BLOQUES) == "Rojo"
    assert rv.buscar_bloque("Nadie, Otro", BLOQUES) is None


def test_cache():
    c, llamadas = rv.Cache(60), []
    f = lambda: llamadas.append(1) or {"ok": True}  # noqa: E731
    assert c.obtener("x", f) == c.obtener("x", f) == {"ok": True}
    assert len(llamadas) == 1
    c.obtener("y", f)
    assert len(llamadas) == 2
