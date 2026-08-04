# Auditoría Monitor Legislativo — Senado — agosto 2026

Repo: `monitor_legistativo_senadores`. Cubre los 4 puntos pedidos: datos
sintéticos, sueldos/presupuesto, revisión de procesos, y agentic AI.

## 1. Resumen ejecutivo

El proyecto está en buen estado: scraper de argentinadatos.com, cálculo de
KPIs por senador/partido/provincia, API FastAPI (`api/run_senado.py`, la que
realmente corre en Railway), dashboard HTML con fallback embebido real, CI/CD
diario y de tests en GitHub Actions. El monitoreo de dieta parlamentaria
(`scripts/monitorear_dieta.py`) lee el recibo oficial en PDF y ya venía
funcionando correctamente antes de esta sesión.

Encontré un solo problema real de integridad de datos, en un archivo que no
está en producción. El resto del repo no tiene datos falsos presentados como
reales.

## 2. Datos sintéticos — hallazgo y fix

**`api/main.py` — riesgo real, pero código muerto.** Era una copia mal pegada
del `api/main.py` del repo hermano de Diputados: importaba `data_loader` e
`indicadores.calculos`, que no existen acá, así que romper al importar era
garantizado. Además el endpoint `/diputados` generaba `asistencia`,
`productividad`, `comisiones` y el score `ice` con `random.randint(...)`
(semilla fija 42) y los devolvía etiquetados `"fuente": "csv_real"` — números
inventados presentados como reales.

Confirmé que **no está montado en producción**: `railway.toml` apunta a
`api.run_senado:app`, no a `api.main:app`, y ningún workflow lo referencia.
Lo dejé como stub que levanta `RuntimeError` al importarse, con el problema
documentado en el docstring, para que nadie lo reviva sin saber esto.

**Todo lo demás revisado, sin problema:**
- `dashboard/senado.html` — el fallback embebido de 72 senadores es real,
  generado por `scripts/actualizar_fallback_senado.py` desde el CSV del día,
  y etiquetado `fuente:'fallback'` (no dice ser dato en vivo cuando no lo es).
- `core/senadores.py` — cálculo de `participation_pct` real a partir de los
  votos scrapeados, sin valores hardcodeados.
- `scraper_senadores.py` (raíz) vs `scrapers/senadores.py` (paquete) —
  ambos tienen los mismos fixes de deduplicación de senadores provinciales;
  no es una versión vieja sin parchear, es un entry point legacy que delega
  en el mismo scraper.

## 3. Sueldos y presupuesto

Verifiqué `dieta.json` y `data/dieta_historial.csv`: el valor del módulo
($2.554,85) no cambió desde enero 2026 hasta el 3 de agosto, pese a que hubo
cobertura de prensa sobre un aumento de la dieta de senadores. Confirmé por
búsqueda web que el aumento fue anunciado en varios medios, pero el **recibo
oficial en PDF que publica el Senado** (la fuente que lee
`scripts/monitorear_dieta.py`) todavía no lo reflejaba — es una demora real
de publicación de la fuente oficial, no un bug del scraper. El script está
corriendo diariamente sin errores.

En vez de dejar esto como una discrepancia silenciosa, la agregué como regla
del agente autónomo (sección 4): si el `periodo` del último recibo leído
queda más de 45 días atrás del mes corriente, se genera un hallazgo
`recibo_oficial_desactualizado` — así la próxima vez que haya un anuncio de
aumento por prensa que tarde en aparecer en el recibo oficial, el agente lo
señala solo, en vez de depender de que alguien lo note a mano.

## 4. Agentic AI

Mismo patrón que el repo de Diputados — dos capas:

**a) Explicaciones en lenguaje natural (Claude, opcional).** `agentic_ai.py`
agrega `explicar_senador()`, `explicar_partido()`, `explicar_provincia()`, y
un dispatcher `explicar(tipo, datos)`. Degrada con gracia sin
`ANTHROPIC_API_KEY`: devuelve `{"disponible": false, "motivo": "..."}` en vez
de romper.

**b) Detección autónoma de anomalías (sin IA, siempre activa).**
`detectar_anomalias()` corre reglas estadísticas sobre la nómina actual:
frescura de datos, composición total ≠72 bancas, provincias con ≠3
senadores, participación crítica individual, outliers estadísticos (IQR),
delta de participación global vs. la corrida anterior, delta de composición,
y la brecha de recibo oficial de dieta descripta arriba.

`scripts/agente_monitor.py` corre esto después del pipeline diario. A
diferencia del repo de Diputados (que sobreescribe un único
`data/diputados.json` y necesita un snapshot aparte), acá cada corrida ya
guarda un CSV nuevo con fecha (`data/senadores_YYYY-MM-DD.csv`), así que el
agente compara directamente los dos CSV más recientes — sin snapshot
adicional.

**Criterio de alerta** (igual al de Diputados, para no spamear por un estado
que ya conocés): hallazgos puntuales (datos desactualizados, composición
incompleta, delta global, recibo desactualizado) alertan siempre que
aparecen en severidad alta; hallazgos por senador/provincia (participación
crítica, outliers, provincia incompleta) solo alertan si son nuevos respecto
a la corrida anterior.

Wireado en:
- `api/run_senado.py`: `GET /ia/status`, `POST /ia/explicar`,
  `GET /ia/anomalias`, `GET /ia/resumen`.
- `.github/workflows/monitor_diario.yml`: paso del agente después del
  scraping, con alerta por email (`dawidd6/action-send-mail`) si hay
  severidad alta nueva, más alerta si el pipeline entero falla (antes este
  workflow no avisaba nada si fallaba).
- `requirements.txt`: agregado `anthropic>=0.40.0` (opcional).

## 5. Procesos — revisión

- `.github/workflows/pipeline_diario.yml` ya estaba auto-documentado como
  deprecado/manual-only; `monitor_diario.yml` es el flujo real y corre bien.
- `cargar_db.py` (carga a Postgres) usa `continue-on-error: true` — correcto,
  la API ya cae a CSV si la DB no está disponible.
- `requirements.txt`: sin drift de versiones — los pines coinciden con lo
  instalado en `.venv` (`fastapi`, `pandas`, `numpy`, `requests`,
  `beautifulsoup4`, `lxml`, `httpx`, `holidays`, `python-dateutil`, `pytest`
  todos al día). `pdfplumber==0.11.4` no está en este `.venv` local, pero sí
  se instala en CI vía `pip install -r requirements.txt` — no es un problema
  del repo, solo hay que correr `pip install -r requirements.txt` localmente
  para tenerlo disponible acá también.
- `test.html` (raíz) — está en `.gitignore`, no se commitea ni se despliega;
  no es una duplicación real de `dashboard/senado.html` en producción.
- `fix_cf.py` (raíz) — script de un solo uso para sacar la ofuscación de
  emails de Cloudflare de `dashboard/indicadores_senadores.html`. Ya cumplió
  su función; lo dejé porque no genera ningún riesgo, pero se puede borrar
  si no lo vas a volver a necesitar.

## 6. Actualización — URL de Railway confirmada

La URL real es `https://monitorlegistativosenadores-production.up.railway.app`
(con la misma variante tipográfica "legistativo" que usa el repo hermano de
Diputados) — no `monitorlegislativosenadores...` como tenía anotado, por eso
no respondía en las verificaciones de esta sesión. Corregida en
`api/run_senado.py` (fallback de `_BASE`) e `INSTRUCCIONES.md`.

Confirmado además: la nueva sección "🤖 Agente" del dashboard
(`dashboard/senado.html`) ya muestra los hallazgos del agente en vivo
(`GET /ia/resumen`), incluyendo el resumen narrativo si está configurado
`ANTHROPIC_API_KEY` en Railway.
