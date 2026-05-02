# 🏛️ Monitor Legislativo — Senado Nacional Argentina

Monitor automático de los **72 senadores nacionales** con indicadores de participación, votaciones y distribución político-territorial. Sin base de datos, sin backend obligatorio — funciona como HTML estático o con FastAPI.

---

## 📐 Arquitectura

```
monitor_legistativo_senadores/
│
├── dashboard/                   # ◀ Frontend HTML estático (Opción A: abrir directo en browser)
│   ├── senado.html              #   Nómina de 72 senadores con filtros, tabla y tarjetas
│   └── indicadores.html         #   KPIs, rankings, gráficos por partido y provincia
│
├── api/
│   ├── main.py                  # API completa (requiere data_loader e indicadores/)
│   └── run_senado.py            # ◀ API standalone solo-senado (recomendado para pruebas)
│
├── core/
│   └── senadores.py             # Lógica de cálculo de indicadores del Senado
│
├── scrapers/
│   └── senadores.py             # Scraper de argentinadatos.com — Senado
│
├── scripts/
│   ├── actualizacion_tel.py     # Actualiza teléfonos de senadores
│   ├── actualizar_bipartisan.py # Calcula índices bipartidistas
│   ├── actualizar_tc.py         # Tasa de conversión proyectos → leyes
│   ├── calendario.py            # Calendario legislativo
│   └── monitorear_dieta.py      # Monitor de dieta parlamentaria
│
├── data/                        # CSVs generados automáticamente (no editar a mano)
│   ├── senadores_YYYY-MM-DD.csv           # Nómina completa con votos
│   ├── reporte_partido_senado_*.csv       # Agregado por bloque político
│   └── reporte_provincial_senado_*.csv    # Agregado por provincia
│
├── scraper_senadores.py         # Entry point del scraper (modo legacy)
├── pipeline.py                  # Pipeline completo de actualización
├── requirements.txt
└── README.md
```

### Flujo de datos

```
argentinadatos.com/api
        │
        ▼
scrapers/senadores.py ──► data/senadores_YYYY-MM-DD.csv
                      ──► data/reporte_partido_senado_*.csv
                      ──► data/reporte_provincial_senado_*.csv
                                │
              ┌─────────────────┴──────────────────┐
              ▼                                     ▼
    api/run_senado.py                    dashboard/senado.html
    GET /senado/senadores                (fallback embebido: 72 senadores)
    GET /senado/reporte-partido          (Opción B: sin servidor)
    GET /senado/reporte-provincial
              │
              ▼
    dashboard/senado.html  ◄─ fetch() al servidor
    dashboard/indicadores.html
```

---

## 🚀 Inicio rápido

### Opción A — Sin servidor (HTML estático)

Los datos de los 72 senadores están **embebidos directamente** en el HTML como fallback. Basta con abrir el archivo en cualquier browser:

```bash
# Clonar y abrir
git clone https://github.com/Viny2030/monitor_legistativo_senadores.git
cd monitor_legistativo_senadores/dashboard
open senado.html          # macOS
xdg-open senado.html      # Linux
start senado.html         # Windows
```

Los datos del fallback se actualizan con cada push al repo (ver pipeline más abajo).

---

### Opción B — Con API FastAPI (datos en tiempo real)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Levantar la API standalone de Senado
python api/run_senado.py
```

La API queda disponible en:

| URL | Descripción |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI interactivo |
| `http://localhost:8000/senado/senadores` | 72 senadores con datos completos |
| `http://localhost:8000/senado/reporte-partido` | Agregado por bloque político |
| `http://localhost:8000/senado/reporte-provincial` | Agregado por provincia |
| `http://localhost:8000/dashboard/senado.html` | Dashboard servido por la API |
| `http://localhost:8000/dashboard/indicadores.html` | Indicadores servidos por la API |

> El dashboard detecta automáticamente si la API está corriendo (`http://localhost:8000`). Si no responde, usa el fallback embebido sin interrumpir la experiencia.

---

## 📊 Dashboard

### `senado.html`
- Tabla completa de los 72 senadores con foto, partido, provincia y métricas
- Filtros en tiempo real: nombre, partido, provincia, rol
- Ranking por participación
- KPIs globales: participación promedio, bloques, votos totales
- Tarjetas por bloque político

### `indicadores.html`
- KPIs: total senadores, participación promedio, bandas alta/media/baja
- Tabla por bloque: barras de participación, votos afirmativos/negativos/abstenciones
- Tabla por provincia: ranking de 24 provincias con participación
- Ranking Top 15 mayor participación
- Ranking 15 menor participación (con datos registrados)

---

## 🔄 Pipeline de actualización

```bash
# Actualizar datos manualmente
python pipeline.py
```

O con el scraper directo:

```bash
python scraper_senadores.py
```

Los CSVs resultantes se guardan en `data/` con la fecha del día. El fallback embebido en los HTML debe actualizarse en cada release (ver sección Contribuir).

### GitHub Actions (automático)

El pipeline corre cada día a las **08:00 hora Argentina** y pushea los nuevos CSVs al repositorio. Ver `.github/workflows/` para la configuración.

---

## 📦 Dependencias

```txt
requests, beautifulsoup4, lxml, httpx   # scraping
pandas, numpy, openpyxl                  # datos
holidays, python-dateutil                # utilitarios
fastapi, uvicorn                         # API (opcional)
```

Instalar todo:
```bash
pip install -r requirements.txt
```

---

## 📐 Indicadores calculados

| Campo | Descripción |
|-------|-------------|
| `participation_pct` | % votos emitidos sobre total de sesiones en período |
| `votos_afirmativos` | Total votos a favor |
| `votos_negativos` | Total votos en contra |
| `abstenciones` | Abstenciones registradas |
| `ausencias` | Sesiones sin presencia |
| `votos_total` | Total sesiones con voto registrado |

La participación se calcula como:
```
participation_pct = (votos_afirmativos + votos_negativos + abstenciones) / votos_total × 100
```

---

## 🗺️ Fuente de datos

- **Nómina y votaciones:** [argentinadatos.com](https://argentinadatos.com) — API pública del Honorable Senado de la Nación Argentina
- **Fotos:** `https://api.argentinadatos.com/static/senado/senadores/{id}.gif`
- **Frecuencia de actualización:** diaria (GitHub Actions) o manual con `pipeline.py`

---

## 🤝 Contribuir

1. Fork del repo
2. Actualizar datos: `python pipeline.py` → nuevos CSVs en `data/`
3. Regenerar fallback HTML: el script `pipeline.py` actualiza `dashboard/senado.html` e `indicadores.html` automáticamente
4. PR con los cambios

---

## 📄 Licencia

MIT — datos públicos del Honorable Senado de la Nación Argentina.
