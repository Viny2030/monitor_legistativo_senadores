"""
red_votos.py — Red de coincidencia de votos entre legisladores.

Grafo de información del sitio: cada legislador es un nodo (con su nombre y su
bloque) y cada línea une a un legislador con los colegas con los que más veces
votó igual en las votaciones nominales del año.

Coincidencia entre A y B = votaciones en las que los dos votaron lo mismo
(afirmativo, negativo o abstención) ÷ votaciones en las que los dos votaron.
Las ausencias no cuentan. Solo se calcula con un mínimo de votaciones en común.

Es un dato descriptivo: votar igual no implica acuerdo político formal ni nada
irregular. El mismo módulo se usa en el sitio de Diputados y en el de Senadores.

Fuente: ArgentinaDatos (actas nominales), https://api.argentinadatos.com
"""
from __future__ import annotations

import re
import time
import unicodedata

import numpy as np

# voto normalizado → código (0 = no votó)
SIN_BLOQUE = "Fuera de la nómina actual"  # votó en el año pero ya no integra la cámara
_CODIGO = {"si": 1, "afirmativo": 1, "no": 2, "negativo": 2, "abstencion": 3}


def normalizar_nombre(nombre: str) -> str:
    """'Yedlin, Pablo Raúl' → 'YEDLIN PABLO RAUL' (sin tildes ni signos)."""
    s = unicodedata.normalize("NFD", str(nombre or "").upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", s)).strip()


def codigo_voto(voto: str) -> int:
    v = unicodedata.normalize("NFD", str(voto or "").lower())
    v = "".join(c for c in v if unicodedata.category(c) != "Mn").strip()
    return _CODIGO.get(v, 0)


def buscar_bloque(nombre: str, bloques: dict) -> str | None:
    """Busca el bloque por nombre normalizado; si no está igual, por apellido +
    primer nombre (las actas y la nómina a veces difieren en segundos nombres)."""
    n = normalizar_nombre(nombre)
    if n in bloques:
        return bloques[n]
    partes = n.split()
    if len(partes) >= 2:
        candidatos = {b for k, b in bloques.items() if k.split()[:2] == partes[:2]}
        if len(candidatos) == 1:
            return candidatos.pop()
    return None


def construir_red(votaciones: list[dict], bloques: dict, k: int = 3, min_comunes: int = 20,
                  periodo: str = "", fuente: str = "") -> dict:
    """
    votaciones: lista de {nombre_legislador: voto} (una por acta nominal).
    bloques:    {nombre_normalizado: bloque}.
    k:          cuántos colegas más parecidos se unen a cada legislador.
    """
    nombres = sorted({n for v in votaciones for n in v})
    if not nombres or not votaciones:
        return {"nodos": [], "aristas": [], "resumen": {"legisladores": 0, "votaciones": 0}}
    idx = {n: i for i, n in enumerate(nombres)}
    V = np.zeros((len(nombres), len(votaciones)), dtype=np.int8)
    for j, acta in enumerate(votaciones):
        for n, voto in acta.items():
            V[idx[n], j] = codigo_voto(voto)

    presentes = (V > 0).astype(np.float32)
    comunes = presentes @ presentes.T
    iguales = sum(((V == c).astype(np.float32) @ (V == c).astype(np.float32).T) for c in (1, 2, 3))
    with np.errstate(divide="ignore", invalid="ignore"):
        coinc = np.where(comunes >= min_comunes, iguales / np.maximum(comunes, 1), np.nan)
    np.fill_diagonal(coinc, np.nan)

    bloque = [buscar_bloque(n, bloques) or SIN_BLOQUE for n in nombres]
    emitidos = presentes.sum(axis=1)

    nodos = []
    for i, n in enumerate(nombres):
        fila = coinc[i]
        mismo = [j for j in range(len(nombres)) if j != i and bloque[j] == bloque[i] and not np.isnan(fila[j])]
        otros = [j for j in range(len(nombres)) if bloque[j] not in (bloque[i], SIN_BLOQUE)
                 and bloque[i] != SIN_BLOQUE and not np.isnan(fila[j])]
        cercano = max(otros, key=lambda j: fila[j]) if otros else None
        nodos.append({
            "id": n, "label": n, "bloque": bloque[i], "votos": int(emitidos[i]),
            "coincidencia_bloque": round(float(np.mean(fila[mismo])) * 100, 1) if mismo else None,
            "coincidencia_otros": round(float(np.mean(fila[otros])) * 100, 1) if otros else None,
            "mas_cercano_otro_bloque": ({"nombre": nombres[cercano], "bloque": bloque[cercano],
                                         "coincidencia": round(float(fila[cercano]) * 100, 1)}
                                        if cercano is not None else None),
        })

    aristas, vistos = [], set()
    for i in range(len(nombres)):
        fila = np.nan_to_num(coinc[i], nan=-1.0)
        for j in np.argsort(-fila)[:k]:
            if fila[j] < 0:
                continue
            par = (min(i, int(j)), max(i, int(j)))
            if par in vistos:
                continue
            vistos.add(par)
            aristas.append({"from": nombres[par[0]], "to": nombres[par[1]],
                            "coincidencia": round(float(coinc[par[0], par[1]]) * 100, 1),
                            "comunes": int(comunes[par[0], par[1]]),
                            "entre_bloques": (bloque[par[0]] != bloque[par[1]]
                                              and SIN_BLOQUE not in (bloque[par[0]], bloque[par[1]]))})

    conteo = {}
    for b in bloque:
        conteo[b] = conteo.get(b, 0) + 1
    return {
        "nodos": nodos, "aristas": aristas,
        "resumen": {
            "legisladores": len(nombres), "votaciones": len(votaciones), "aristas": len(aristas),
            "entre_bloques": sum(a["entre_bloques"] for a in aristas), "k": k, "min_comunes": min_comunes,
            "periodo": periodo, "fuente": fuente,
            "bloques": sorted(({"bloque": b, "legisladores": c} for b, c in conteo.items()),
                              key=lambda x: -x["legisladores"]),
            "sin_bloque": conteo.get(SIN_BLOQUE, 0),
        },
    }


class Cache:
    """Guarda el resultado unas horas: la red se arma con cientos de actas."""

    def __init__(self, segundos: int = 6 * 3600):
        self.segundos, self.valor, self.cuando, self.clave = segundos, None, 0.0, None

    def obtener(self, clave, calcular):
        if self.valor is not None and self.clave == clave and time.time() - self.cuando < self.segundos:
            return self.valor
        self.valor, self.clave, self.cuando = calcular(), clave, time.time()
        return self.valor
