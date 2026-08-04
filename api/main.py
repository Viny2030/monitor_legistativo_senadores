"""
api/main.py — DEPRECADO, no usar. No está montado en producción.

Este archivo es una copia mal pegada del api/main.py del repo hermano
monitor_legistativo (Diputados): importa `from data_loader import
construir_datos` y `from indicadores.calculos import calcular_todos`, dos
módulos que NO existen en este repo — cualquier intento de levantar esta
app (uvicorn api.main:app) revienta en el import, antes de servir un solo
request. No está referenciado en railway.toml (que apunta a
api.run_senado:app) ni en ningún workflow de .github/.

Además tenía un problema serio de integridad de datos que conviene dejar
documentado por si alguien lo retoma: el endpoint /diputados generaba
`asistencia`, `productividad`, `comisiones` y el score `ice` con
`random.randint(...)` (semilla fija 42) y los devolvía con
`"fuente": "csv_real"` — números inventados etiquetados como si fueran
datos reales del scraper. Si en algún momento se rescata este archivo
(no debería hacer falta: api/run_senado.py ya cubre /senado/* con datos
reales desde CSV/Postgres), ese endpoint /diputados no corresponde a este
repo (es de Diputados, no de Senadores) y en cualquier caso habría que
sacarle el random y el fuente mal etiquetado.

La API real de este repo es api/run_senado.py — ver railway.toml y
README.md.
"""

raise RuntimeError(
    "api/main.py está deprecado y no se usa en este repo. "
    "La API real es api/run_senado.py (uvicorn api.run_senado:app). "
    "Ver el docstring de este archivo para más contexto."
)
