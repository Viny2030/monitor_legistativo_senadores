"""
scripts/agente_monitor.py — Agente autónomo de monitoreo (Senado).

Corre después del pipeline diario (pipeline.py). A diferencia del repo
hermano de Diputados (que sobrescribe un único data/diputados.json), este
repo ya guarda un CSV nuevo por día en data/senadores_YYYY-MM-DD.csv — así
que no hace falta un snapshot aparte para comparar corridas: el CSV de hoy y
el CSV anterior más reciente (los dos últimos por fecha de nombre de
archivo) ya cumplen ese rol.

El agente:
  1. Detecta anomalías con reglas estadísticas (siempre corre, no necesita
     ANTHROPIC_API_KEY): participación crítica, outliers, composición
     incompleta (≠72 bancas o alguna provincia ≠3 senadores), datos
     desactualizados, deltas vs. la corrida anterior, y brecha entre un
     aumento de dieta anunciado y el recibo oficial publicado (dieta.json).
  2. Si hay ANTHROPIC_API_KEY, le pide a Claude un resumen ejecutivo en
     lenguaje natural de esos hallazgos.

Esto es lo que lo hace "agente" y no solo un endpoint: se dispara solo
(GitHub Action, cron, o manualmente) y decide si hay algo para reportar sin
que nadie tenga que preguntarle.

Salidas:
  - data/alertas_agente_senado.json → último resultado completo (para el dashboard)
  - stdout                          → resumen legible (para logs de CI)
  - exit code 1 si hay algo que amerita mandar el mail de alerta (ver
    decidir_alerta() abajo), exit code 0 en cualquier otro caso.

Criterio de alerta (mismo patrón que el repo de Diputados, para no repetir el
mismo mail todos los días por una condición que ya conocés):

  - Hallazgos "puntuales/urgentes" (datos_desactualizados, datos_sin_metadata,
    delta_participacion_global, delta_composicion, composicion_incompleta,
    recibo_oficial_desactualizado) alertan SIEMPRE que aparezcan en severidad
    alta — son eventos, no estados persistentes.
  - Hallazgos "por senador/provincia" (participacion_critica,
    outlier_estadistico_participacion, provincia_incompleta) solo alertan si
    son NUEVOS respecto a la corrida anterior. Si un senador sigue con
    participación crítica diez días seguidos, alertó el primer día — del
    segundo en adelante queda solo registrado en
    data/alertas_agente_senado.json, sin spam de mail.

Uso:
    python scripts/agente_monitor.py
"""
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentic_ai import resumen_diario  # noqa: E402

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DIETA_FILE = BASE_DIR / "dieta.json"
ALERTAS_FILE = DATA_DIR / "alertas_agente_senado.json"

TIPOS_SIEMPRE_ALERTA = {
    "datos_desactualizados",
    "datos_sin_metadata",
    "delta_participacion_global",
    "delta_composicion",
    "composicion_incompleta",
    "recibo_oficial_desactualizado",
}
TIPOS_SOLO_SI_NUEVO = {
    "participacion_critica",
    "outlier_estadistico_participacion",
    "provincia_incompleta",
}


def _identidad_hallazgo(h: dict) -> tuple:
    """Clave estable para comparar el mismo hallazgo entre corridas."""
    return (h.get("tipo"), h.get("senador") or h.get("provincia") or h.get("detalle"))


def decidir_alerta(analisis: dict, alertas_anteriores) -> tuple:
    """
    Devuelve (requiere_alerta, hallazgos_relevantes) aplicando el criterio de
    arriba. hallazgos_relevantes es el subconjunto de hallazgos alta que
    justifica el mail — útil para loguear *por qué* se alertó, no solo que
    se alertó.
    """
    ids_alta_anteriores = set()
    if alertas_anteriores:
        analisis_ant = alertas_anteriores.get("analisis", {}) or {}
        for h in analisis_ant.get("hallazgos", []):
            if h.get("severidad") == "alta":
                ids_alta_anteriores.add(_identidad_hallazgo(h))

    relevantes = []
    for h in analisis.get("hallazgos", []):
        if h.get("severidad") != "alta":
            continue
        tipo = h.get("tipo")
        if tipo in TIPOS_SIEMPRE_ALERTA:
            relevantes.append(h)
        elif tipo in TIPOS_SOLO_SI_NUEVO:
            if _identidad_hallazgo(h) not in ids_alta_anteriores:
                relevantes.append(h)
        else:
            # Tipo no clasificado todavía (por si se agregan reglas nuevas
            # más adelante) — mejor pecar de cauteloso y alertar.
            relevantes.append(h)

    return (len(relevantes) > 0, relevantes)


def _cargar_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  No se pudo leer {path}: {e}")
        return None


def _listar_csv_nomina() -> list:
    """Los dos CSV de nómina más recientes por fecha de nombre de archivo
    (data/senadores_YYYY-MM-DD.csv), más reciente primero."""
    archivos = sorted(glob.glob(str(DATA_DIR / "senadores_*.csv")), reverse=True)
    return [Path(a) for a in archivos]


def _fecha_de_nombre(path: Path):
    m = re.search(r"senadores_(\d{4}-\d{2}-\d{2})\.csv$", path.name)
    return m.group(1) if m else None


def _cargar_csv(path: Path) -> list:
    """Misma normalización de campos que GET /senado/senadores en
    api/run_senado.py — para que las reglas de agentic_ai.py trabajen sobre
    el mismo formato que ya consume la API."""
    import pandas as pd

    df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")

    def safe_int(v):
        try:
            return int(float(v)) if pd.notna(v) else 0
        except Exception:
            return 0

    def safe_float(v):
        try:
            return float(v) if pd.notna(v) else None
        except Exception:
            return None

    registros = []
    for _, row in df.iterrows():
        registros.append({
            "nombre":            str(row.get("nombre", "—")),
            "provincia":         str(row.get("provincia", "—")),
            "partido":           str(row.get("partido_normalizado", row.get("partido", "—"))),
            "rol_provincial":    str(row.get("rol_provincial", "—")),
            "votos_total":       safe_int(row.get("votos_total")),
            "votos_afirmativos": safe_int(row.get("votos_afirmativos")),
            "votos_negativos":   safe_int(row.get("votos_negativos")),
            "abstenciones":      safe_int(row.get("abstenciones")),
            "ausencias":         safe_int(row.get("ausencias")),
            "participation_pct": safe_float(row.get("participation_pct")),
        })
    return registros


def main() -> int:
    csvs = _listar_csv_nomina()
    if not csvs:
        print(f"❌ No se encontró ningún data/senadores_*.csv — correr pipeline.py primero.")
        return 2

    csv_actual = csvs[0]
    csv_anterior = csvs[1] if len(csvs) > 1 else None

    senadores_actual = _cargar_csv(csv_actual)
    senadores_anterior = _cargar_csv(csv_anterior) if csv_anterior else None
    fecha_datos = _fecha_de_nombre(csv_actual)
    dieta = _cargar_json(DIETA_FILE)

    # Se carga ANTES de sobreescribir ALERTAS_FILE más abajo, para poder
    # comparar los hallazgos de hoy contra los de la corrida anterior.
    alertas_anteriores = _cargar_json(ALERTAS_FILE)

    print("=" * 60)
    print("=== Agente de Monitoreo — Monitor Legislativo Senado ===")
    print("=" * 60)
    print(f"Nómina actual: {csv_actual.name} ({len(senadores_actual)} senadores)")
    print(f"Nómina anterior: {csv_anterior.name if csv_anterior else 'no disponible (primera corrida)'}")
    print(f"dieta.json: {'encontrado' if dieta else 'no encontrado'}")

    resultado = resumen_diario(senadores_actual, senadores_anterior, dieta, fecha_datos)
    analisis = resultado["analisis"]

    print(f"\nHallazgos: {analisis['total_hallazgos']} "
          f"(alta: {analisis['por_severidad']['alta']}, "
          f"media: {analisis['por_severidad']['media']}, "
          f"baja: {analisis['por_severidad']['baja']})")
    for h in analisis["hallazgos"]:
        print(f"  [{h['severidad'].upper():5s}] {h['tipo']}: {h['detalle']}")

    if resultado["narrativa"] and resultado["narrativa"].get("disponible"):
        print("\n--- Resumen ejecutivo (Claude) ---")
        print(resultado["narrativa"]["explicacion"])
    elif resultado["narrativa"]:
        print(f"\n(sin resumen narrativo: {resultado['narrativa'].get('motivo')})")

    requiere_alerta, hallazgos_relevantes = decidir_alerta(analisis, alertas_anteriores)
    resultado["alerta"] = {
        "requiere_alerta": requiere_alerta,
        "criterio": "siempre para eventos puntuales; solo si es nuevo para estados por senador/provincia",
        "hallazgos_relevantes": hallazgos_relevantes,
    }
    print(f"\n{'🚨' if requiere_alerta else 'ℹ️ '} "
          f"{'Se dispara el mail de alerta' if requiere_alerta else 'No hace falta mandar mail'} "
          f"({len(hallazgos_relevantes)} hallazgo(s) relevante(s) de {analisis['por_severidad']['alta']} en severidad alta)")
    for h in hallazgos_relevantes:
        print(f"    → {h['tipo']}: {h['detalle']}")

    DATA_DIR.mkdir(exist_ok=True)
    with open(ALERTAS_FILE, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Resultado completo guardado en {ALERTAS_FILE}")

    return 1 if requiere_alerta else 0


if __name__ == "__main__":
    sys.exit(main())
