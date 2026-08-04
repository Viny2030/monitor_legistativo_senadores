"""
agentic_ai.py — Agentic AI para el Monitor Legislativo (Senado).

Mismo patrón que el repo hermano monitor_legistativo (Diputados): usa la API
de Anthropic (Claude) para generar explicaciones narrativas en lenguaje
natural sobre los datos que ya calcula el resto del sistema (core/senadores.py
y scripts/monitorear_dieta.py), sin volver a tocar los datos.

Degradación elegante: si no está configurada ANTHROPIC_API_KEY, o falla la
librería `anthropic`, todas las llamadas devuelven
{"disponible": False, "motivo": "..."} en vez de romper el endpoint.

El módulo también actúa de forma autónoma: `detectar_anomalias()` y
`resumen_diario()` no dependen de Claude — analizan la nómina de senadores
(CSV) y dieta.json con reglas estadísticas simples (IQR, umbrales,
comparación contra la corrida anterior) y devuelven hallazgos estructurados.
Si hay ANTHROPIC_API_KEY, `resumen_diario()` además le pide a Claude que
redacte esos hallazgos en lenguaje natural; si no, el agente sigue siendo
útil (solo sin la prosa). Esto es lo que permite correrlo sin pedido humano
(cron/GitHub Action) en scripts/agente_monitor.py.
"""

import os
import re
import statistics
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

try:
    import anthropic
    _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except ImportError:
    anthropic = None
    _client = None


def ia_disponible() -> bool:
    """True si hay librería `anthropic` instalada Y ANTHROPIC_API_KEY configurada."""
    return _client is not None


def _no_disponible(motivo: str) -> dict:
    return {"disponible": False, "motivo": motivo}


def _pedir_a_claude(system: str, prompt: str, max_tokens: int = 500) -> dict:
    if not ia_disponible():
        if anthropic is None:
            return _no_disponible(
                "La librería 'anthropic' no está instalada en este entorno."
            )
        return _no_disponible(
            "ANTHROPIC_API_KEY no está configurada — el asistente de IA está deshabilitado."
        )
    try:
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(
            bloque.text for bloque in resp.content if getattr(bloque, "type", "") == "text"
        )
        return {"disponible": True, "explicacion": texto.strip()}
    except Exception as e:
        return _no_disponible(f"Error al consultar la IA: {e}")


_SYSTEM_BASE = (
    "Sos un analista de transparencia legislativa que explica, en español "
    "rioplatense claro y sin tecnicismos innecesarios, indicadores algorítmicos "
    "sobre el desempeño del Senado de la Nación Argentina (participación en "
    "votaciones, distribución de bancas por partido y provincia, dieta "
    "parlamentaria). No acusás a nadie de mal desempeño: describís qué "
    "significa el número, por qué es relevante para la rendición de cuentas "
    "(no una determinación de responsabilidad), y qué pregunta de control "
    "ciudadano ayudaría a contextualizarlo. Sé concreto y breve (4-8 líneas)."
)


def explicar_senador(perfil: dict) -> dict:
    """
    Explica el perfil de un senador/a individual.
    perfil: dict tal cual lo devuelve /senado/senadores (un elemento de la lista).
    """
    prompt = f"""Perfil del senador/a "{perfil.get('nombre', '—')}" (partido {perfil.get('partido', '—')}, provincia {perfil.get('provincia', '—')}, rol {perfil.get('rol_provincial', '—')}):

- Participación en votaciones: {perfil.get('participation_pct', '—')}%
- Votos afirmativos: {perfil.get('votos_afirmativos', '—')}
- Votos negativos: {perfil.get('votos_negativos', '—')}
- Abstenciones: {perfil.get('abstenciones', '—')}
- Ausencias: {perfil.get('ausencias', '—')}

Explicá qué indica este perfil sobre el desempeño legislativo de este senador/a
y qué habría que contextualizar (por ejemplo: antigüedad en el cargo, comisión
que integra, licencias) antes de sacar conclusiones."""
    return _pedir_a_claude(_SYSTEM_BASE, prompt)


def explicar_partido(perfil: dict) -> dict:
    """
    Explica el desempeño agregado de un bloque/partido.
    perfil: dict tal cual lo devuelve /senado/reporte-partido (un elemento de la lista).
    """
    prompt = f"""Bloque/partido "{perfil.get('partido', '—')}":

- Bancas: {perfil.get('bancas', '—')}
- Participación promedio: {perfil.get('participation_pct', '—')}%
- Votos afirmativos totales: {perfil.get('votos_afirmativos', '—')}
- Votos negativos totales: {perfil.get('votos_negativos', '—')}
- Abstenciones totales: {perfil.get('abstenciones', '—')}

Explicá qué indica este perfil sobre el peso político y la disciplina de voto
del bloque, y qué pregunta de control ciudadano ayudaría a profundizarlo."""
    return _pedir_a_claude(_SYSTEM_BASE, prompt)


def explicar_provincia(perfil: dict) -> dict:
    """
    Explica el desempeño agregado de una provincia (3 bancas c/u).
    perfil: dict tal cual lo devuelve /senado/reporte-provincial (un elemento de la lista).
    """
    prompt = f"""Provincia "{perfil.get('provincia', '—')}":

- Senadores registrados: {perfil.get('senadores', '—')} (esperado: 3)
- Partidos representados: {perfil.get('partidos', '—')}
- Participación promedio: {perfil.get('participation_pct', '—')}%

Explicá qué indica este perfil sobre la representación territorial de la
provincia en el Senado, y si la cantidad de senadores registrados amerita
alguna aclaración de calidad de dato."""
    return _pedir_a_claude(_SYSTEM_BASE, prompt)


def explicar(tipo: str, datos: dict) -> dict:
    """Punto de entrada genérico único (mismo patrón que el repo de Diputados)."""
    if tipo == "partido":
        return explicar_partido(datos or {})
    if tipo == "provincia":
        return explicar_provincia(datos or {})
    return explicar_senador(datos or {})


# ---------------------------------------------------------------------------
# Detección autónoma de anomalías — no requiere Claude ni pedido humano.
# ---------------------------------------------------------------------------
BANCAS_SENADO = 72
SENADORES_POR_PROVINCIA = 3

UMBRAL_PARTICIPACION_CRITICA = 40.0   # % por debajo del cual se marca ausentismo crítico
UMBRAL_DATOS_DESACTUALIZADOS_DIAS = 10
UMBRAL_RECIBO_DESACTUALIZADO_DIAS = 45   # brecha "aumento anunciado" vs recibo oficial publicado
MAX_HALLAZGOS_POR_TIPO = 10

_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _severidad(valor: float, umbral: float, muy_grave_a: float) -> str:
    return "alta" if valor <= muy_grave_a else "media" if valor <= umbral else "baja"


def _outliers_iqr(valores_con_id: list) -> list:
    """Devuelve los valores por debajo de Q1 - 1.5*IQR (outliers bajos)."""
    if len(valores_con_id) < 8:
        return []  # muestra muy chica para IQR confiable
    valores = sorted(v for _, v in valores_con_id)
    q1 = statistics.quantiles(valores, n=4)[0]
    q3 = statistics.quantiles(valores, n=4)[2]
    iqr = q3 - q1
    piso = q1 - 1.5 * iqr
    return [{"id": ident, "valor": v, "piso_iqr": round(piso, 2)}
            for ident, v in valores_con_id if v < piso]


def _dias_desde_fecha(fecha_str: str, formato: str = "%Y-%m-%d") -> float:
    try:
        dt = datetime.strptime(fecha_str, formato)
        return (datetime.now() - dt).total_seconds() / 86400
    except Exception:
        return None


def _dias_desde_periodo(periodo: str) -> float:
    """
    periodo viene como "Enero 2026" (ver scripts/monitorear_dieta.py). Devuelve
    cuántos días pasaron desde el día 1 de ese mes hasta hoy — sirve para
    detectar un recibo oficial que quedó "viejo" (por ejemplo, porque el
    Senado anunció un aumento por prensa pero todavía no publicó el recibo
    correspondiente).
    """
    if not periodo:
        return None
    m = re.match(r"([A-Za-zÁÉÍÓÚáéíóú]+)\s+(\d{4})", periodo.strip())
    if not m:
        return None
    mes_nombre, anio = m.group(1).lower(), int(m.group(2))
    mes = _MESES_ES.get(mes_nombre)
    if not mes:
        return None
    try:
        dt = datetime(anio, mes, 1)
        return (datetime.now() - dt).total_seconds() / 86400
    except Exception:
        return None


def detectar_anomalias(senadores: list, senadores_anterior: list = None,
                        dieta: dict = None, fecha_datos: str = None) -> dict:
    """
    Analiza la nómina de senadores (lista de dicts, mismo formato que
    /senado/senadores) con reglas estadísticas simples — sin llamar a Claude,
    sin costo, apto para correr en cada actualización del pipeline.

    senadores_anterior (opcional): misma lista, de la corrida previa —
    habilita detección de deltas (caídas de participación, cambios de
    composición).
    dieta (opcional): dict tal cual dieta.json — habilita la detección de
    brecha entre un aumento anunciado y el recibo oficial publicado.
    fecha_datos (opcional): fecha (YYYY-MM-DD) del CSV de nómina usado —
    habilita la detección de datos desactualizados.

    Devuelve {"generado_en": iso, "total_hallazgos": n, "hallazgos": [...]}
    con cada hallazgo: {tipo, severidad (alta/media/baja), detalle, ...}.
    """
    hallazgos = []
    senadores = senadores or []

    # 1) Frescura de los datos (fecha del CSV de nómina usado)
    if fecha_datos:
        dias = _dias_desde_fecha(fecha_datos)
        if dias is not None and dias > UMBRAL_DATOS_DESACTUALIZADOS_DIAS:
            hallazgos.append({
                "tipo": "datos_desactualizados",
                "severidad": "alta" if dias > 30 else "media",
                "detalle": f"El CSV de nómina más reciente es de hace {dias:.1f} días "
                           f"(fecha: {fecha_datos}). Revisar el pipeline diario.",
            })
    else:
        hallazgos.append({
            "tipo": "datos_sin_metadata",
            "severidad": "media",
            "detalle": "No se pudo determinar la fecha del CSV de nómina usado — "
                       "no se puede verificar frescura del dato.",
        })

    # 2) Composición total distinta a 72 bancas
    total = len(senadores)
    if total != BANCAS_SENADO:
        hallazgos.append({
            "tipo": "composicion_incompleta",
            "severidad": "alta" if abs(total - BANCAS_SENADO) > 5 else "media",
            "detalle": f"La nómina tiene {total} senadores (esperado {BANCAS_SENADO}) — "
                       f"revisar si es un problema de scraping o un cambio real de composición.",
        })

    # 3) Provincias con ≠ 3 senadores (dato faltante en la fuente)
    por_provincia = {}
    for s in senadores:
        prov = s.get("provincia", "—")
        por_provincia[prov] = por_provincia.get(prov, 0) + 1
    incompletas = sorted(
        (p for p in por_provincia.items() if p[1] != SENADORES_POR_PROVINCIA),
        key=lambda p: p[1]
    )[:MAX_HALLAZGOS_POR_TIPO]
    for prov, cant in incompletas:
        hallazgos.append({
            "tipo": "provincia_incompleta",
            "severidad": "media",
            "detalle": f"{prov}: {cant} senador(es) registrado(s) (esperado 3) — "
                       f"posible dato faltante en la fuente (argentinadatos.com).",
            "provincia": prov,
        })

    # 4) Participación crítica individual
    con_participacion = [s for s in senadores if s.get("participation_pct") is not None]
    criticos = sorted(
        (s for s in con_participacion if s["participation_pct"] < UMBRAL_PARTICIPACION_CRITICA),
        key=lambda s: s["participation_pct"]
    )[:MAX_HALLAZGOS_POR_TIPO]
    for s in criticos:
        hallazgos.append({
            "tipo": "participacion_critica",
            "severidad": _severidad(s["participation_pct"], UMBRAL_PARTICIPACION_CRITICA, 20.0),
            "detalle": f"{s.get('nombre', '?')} ({s.get('partido', '?')}, {s.get('provincia', '?')}): "
                       f"participación {s['participation_pct']}%.",
            "senador": s.get("nombre"),
        })

    # 5) Outliers estadísticos de participación (IQR) — captura casos que no
    #    bajan del umbral fijo pero sí se despegan mucho del resto del cuerpo.
    pares_participacion = [(s.get("nombre", "?"), s["participation_pct"]) for s in con_participacion]
    for o in _outliers_iqr(pares_participacion)[:MAX_HALLAZGOS_POR_TIPO]:
        hallazgos.append({
            "tipo": "outlier_estadistico_participacion",
            "severidad": "baja",
            "detalle": f"{o['id']}: participación {o['valor']}%, por debajo del piso estadístico "
                       f"({o['piso_iqr']}%) del resto del cuerpo.",
            "senador": o["id"],
        })

    # 6) Comparación contra la corrida anterior (si se provee)
    if senadores_anterior:
        part_ant = [s["participation_pct"] for s in senadores_anterior if s.get("participation_pct") is not None]
        part_act = [s["participation_pct"] for s in con_participacion]
        if part_ant and part_act:
            prom_ant = statistics.mean(part_ant)
            prom_act = statistics.mean(part_act)
            delta = prom_act - prom_ant
            if abs(delta) >= 5.0:
                hallazgos.append({
                    "tipo": "delta_participacion_global",
                    "severidad": "alta" if abs(delta) >= 10 else "media",
                    "detalle": f"Participación promedio global {'subió' if delta > 0 else 'cayó'} "
                               f"{abs(round(delta, 1))} puntos vs. la corrida anterior "
                               f"({round(prom_ant, 1)}% → {round(prom_act, 1)}%).",
                })

        n_ant, n_act = len(senadores_anterior), len(senadores)
        if n_ant and n_act and n_ant != n_act:
            hallazgos.append({
                "tipo": "delta_composicion",
                "severidad": "media",
                "detalle": f"La cantidad de senadores en el dataset cambió de {n_ant} a {n_act} "
                           f"entre corridas — revisar si es una actualización real de composición "
                           f"o un problema del scraper (datos parciales).",
            })

    # 7) Brecha "aumento anunciado por prensa" vs recibo oficial publicado.
    #    El Senado a veces confirma un aumento por prensa antes de publicar el
    #    recibo oficial (PDF) que sustenta el valor del módulo. Si el período
    #    del último recibo leído (dieta.json → "periodo") quedó muy atrás del
    #    mes corriente, lo marcamos — no es un error del scraper, es una
    #    demora real de la fuente oficial que conviene visibilizar.
    if dieta:
        periodo = dieta.get("periodo", "")
        dias_periodo = _dias_desde_periodo(periodo)
        if dias_periodo is not None and dias_periodo > UMBRAL_RECIBO_DESACTUALIZADO_DIAS:
            hallazgos.append({
                "tipo": "recibo_oficial_desactualizado",
                "severidad": "media",
                "detalle": f"El último recibo oficial leído corresponde a \"{periodo}\" "
                           f"({dias_periodo:.0f} días atrás). Si hubo un aumento de dieta "
                           f"anunciado por prensa después de ese período, todavía no está "
                           f"reflejado en dieta.json — conviene verificar manualmente contra "
                           f"{('https://www.senado.gob.ar/prensa/adjunto/descargarArchivo/tipo/Dieta')}.",
            })
        elif not periodo:
            hallazgos.append({
                "tipo": "recibo_sin_periodo",
                "severidad": "baja",
                "detalle": "dieta.json no tiene el campo 'periodo' — no se puede verificar "
                           "antigüedad del recibo oficial leído.",
            })

    orden_severidad = {"alta": 0, "media": 1, "baja": 2}
    hallazgos.sort(key=lambda h: orden_severidad.get(h["severidad"], 3))

    return {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "total_hallazgos": len(hallazgos),
        "por_severidad": {
            s: sum(1 for h in hallazgos if h["severidad"] == s)
            for s in ("alta", "media", "baja")
        },
        "hallazgos": hallazgos,
    }


def resumen_diario(senadores: list, senadores_anterior: list = None,
                    dieta: dict = None, fecha_datos: str = None) -> dict:
    """
    Punto de entrada del agente autónomo: corre detectar_anomalias() (siempre
    funciona, no depende de Claude) y, si hay IA disponible, le pide a Claude
    que redacte un resumen ejecutivo en lenguaje natural de esos hallazgos
    para mandar por email o mostrar en el dashboard.
    """
    analisis = detectar_anomalias(senadores, senadores_anterior, dieta, fecha_datos)

    resultado = {
        "generado_en": analisis["generado_en"],
        "total_senadores": len(senadores or []),
        "analisis": analisis,
        "narrativa": None,
    }

    if analisis["total_hallazgos"] == 0:
        resultado["narrativa"] = {
            "disponible": True,
            "explicacion": "Sin anomalías detectadas en esta corrida: participación, "
                           "composición y frescura de datos dentro de los rangos esperados.",
        }
        return resultado

    if not ia_disponible():
        resultado["narrativa"] = _no_disponible(
            "Hallazgos estructurados generados sin problema (no requieren IA); "
            "la redacción narrativa está deshabilitada porque no hay ANTHROPIC_API_KEY."
        )
        return resultado

    resumen_hallazgos = "\n".join(
        f"- [{h['severidad'].upper()}] {h['tipo']}: {h['detalle']}"
        for h in analisis["hallazgos"][:15]
    )
    prompt = f"""El agente de monitoreo detectó {analisis['total_hallazgos']} hallazgos en la
corrida de hoy sobre el Senado de la Nación (Alta: {analisis['por_severidad']['alta']},
Media: {analisis['por_severidad']['media']}, Baja: {analisis['por_severidad']['baja']}):

{resumen_hallazgos}

Redactá un resumen ejecutivo breve (6-10 líneas) para un email de alerta interno,
priorizando lo de severidad alta y media. No es una acusación a ningún senador
puntual: encuadralo como control de calidad de datos y seguimiento de transparencia."""

    resultado["narrativa"] = _pedir_a_claude(_SYSTEM_BASE, prompt, max_tokens=400)
    return resultado
