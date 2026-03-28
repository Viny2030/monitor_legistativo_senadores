# 🏛️ Monitor Legislativo — Senado de la Nación Argentina

**Versión 1.0 · Marzo 2026**

Monitor de eficiencia legislativa y transparencia presupuestaria del Honorable Senado de la Nación Argentina. Analiza la composición y el desempeño de los 72 senadores en ejercicio a partir de registros oficiales del HSN, el SIL y la OPC.

---

## 📊 Dashboard

| Archivo | Descripción |
|---------|-------------|
| `dashboard/indicadores_senadores.html` | Nómina completa, composición por bloque y provincia, 12 indicadores en 4 dimensiones, donación |
| `dashboard/indicadores2_senadores.html` | Todos los indicadores de cámara y bloque con datos reales 2025 |
| `dashboard/indicadores_bloques_senadores.html` | Indicadores calculados automáticamente por bloque, tabla ordenable, 4 rankings |
| `dashboard/nomina_detalle_senadores.html` | Cards individuales con 8 indicadores activos, vista cards/lista, filtros |
| `dashboard/metodologia_senadores.html` | Marco institucional, diferencias vs Diputados, fórmulas, fuentes, bibliografía |
| `dashboard/manual_senadores.html` | Guía completa de uso del monitor |

---

## 📐 Indicadores — estado v1.0

### ✅ Activos (datos reales 2025)

| Código | Nombre | Valor 2025 | Fuente |
|--------|--------|-----------|--------|
| NEP | Número Efectivo de Partidos | calculado en tiempo real | HSN nómina oficial |
| IF | Índice de Fragmentación (Rae) | calculado en tiempo real | HSN nómina oficial |
| IRB | Tasa de Renovación por Tercio | 33,3% (Grupo III — 24 bancas) | CN Art. 56 · elecciones 26/10/2025 |
| IRG | Representación Geográfica | igualitaria — 3/provincia | CN Art. 54 |
| CRC | Costo por Ciudadano | ~$2.890 / hab. | DA 3/2025 · INDEC |
| RLS | Legislación Sustantiva | 72,7% · 3 insistencias históricas | Directorio Legislativo 2025 |
| COLS | Costo por Ley Sancionada | ~$10.446 MM / ley | DA 3/2025 · Dir. Legislativo |
| ECO | Efectividad del Control | 3/3 insistencias + 2 pliegos rechazados | senado.gob.ar/votaciones |
| IAD | Accesibilidad Documental | 4/5 — JSON + Excel disponibles | senado.gob.ar/DatosAbiertos |
| TVD | Veracidad de Datos | ~98% nómina verificada | JSON oficial HSN |

### ⚠️ Estimación parcial

| Código | Nombre | Estado |
|--------|--------|--------|
| IAP | Autonomía Presupuestaria | ~0,92 estimado — ejecución exacta en PDFs trimestrales HSN |
| RPS | Profesionalización del Staff | pendiente desglose planta/transitorio RRHH HSN |
| NAPE | Asistencia Efectiva | estimación parcial — dato exacto en estadísticas HSN |

### 🔜 Planificado v2.0

| Código | Nombre | Versión |
|--------|--------|---------|
| TPMP | Maduración de Proyectos | v1.1 — requiere SIL |
| ITC | Trabajo en Comisiones | v1.1 — requiere actas comisión |
| IPCV | Participación Ciudadana Virtual | v2.0 — módulo ciudadano Q3 2026 |

---

## 🏛️ Marco constitucional

| Característica | Senado | Diputados |
|---|---|---|
| Composición | 72 senadores | 257 diputados |
| Representación | 3 por provincia (igualitaria) | Proporcional a la población |
| Mandato | 6 años | 4 años |
| Renovación | Por tercios cada 2 años | Por mitades cada 2 años |
| Quórum | 37 (mayoría de 72) | 129 (mayoría de 257) |
| Sistema electoral | 2+1 (mayoría + minoría) | D'Hondt proporcional |
| Open Data | JSON + Excel disponibles | Solo PDF + HTML |

### Grupos de renovación por tercios

- **Grupo I (2021–2027):** Catamarca, Córdoba, Corrientes, Chubut, La Pampa, Mendoza, Santa Fe, Tucumán
- **Grupo II (2023–2029):** Buenos Aires, Formosa, Jujuy, La Rioja, Misiones, San Juan, San Luis, Santa Cruz
- **Grupo III (2025–2031):** Chaco, CABA, Entre Ríos, Neuquén, Río Negro, Salta, Santiago del Estero, Tierra del Fuego

---

## 🗂️ Estructura del repositorio

```
monitor_legistativo_senadores/
├── dashboard/
│   ├── indicadores_senadores.html
│   ├── indicadores2_senadores.html
│   ├── indicadores_bloques_senadores.html
│   ├── nomina_detalle_senadores.html
│   ├── metodologia_senadores.html
│   └── manual_senadores.html
├── foto.jpg
└── README.md
```

---

## ⚙️ Uso local

No requiere servidor. Clonar el repositorio y abrir cualquier archivo HTML directamente en el navegador:

```bash
git clone https://github.com/Viny2030/monitor_legistativo_senadores.git
```

```
file:///ruta/al/repo/dashboard/indicadores_senadores.html
```

### Actualización de datos

Los indicadores de composición (NEP, IF, IRB) se recalculan automáticamente en el navegador. Para actualizar la nómina:

1. Descargar el JSON oficial: `senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoSenadores/json`
2. Reemplazar el array `SENADORES` en los archivos HTML
3. Los indicadores se recalculan al recargar la página

### Frecuencia recomendada

| Dato | Frecuencia | Evento disparador |
|------|-----------|-------------------|
| Nómina de senadores | Por tercios | Renovación de diciembre (años impares) |
| Cambios de bloque | Mensual | Altas, bajas, fusiones |
| CRC / COLS | Anual | Aprobación del presupuesto |
| RLS / ECO | Anual | Balance legislativo de fin de año |

---

## 📚 Fuentes de datos

| Fuente | URL | Datos |
|--------|-----|-------|
| HSN — Bloques | [senado.gob.ar/senadores](https://www.senado.gob.ar/senadores/listados/agrupados-por-bloques) | Nómina, bloque, provincia |
| HSN — JSON abierto | [DatosAbiertos/json](https://www.senado.gob.ar/micrositios/DatosAbiertos/ExportarListadoSenadores/json) | Nómina estructurada |
| HSN — Presupuesto | [administrativo/partida](https://www.senado.gob.ar/administrativo/partida) | Partidas y ejecución trimestral |
| HSN — Estadísticas | [parlamentario/estadisticas](https://www.senado.gob.ar/parlamentario/estadisticas) | Asistencia, sesiones |
| OPC | [opc.gob.ar](https://opc.gob.ar) | Análisis presupuestario |
| Directorio Legislativo | [directoriolegislativo.org](https://directoriolegislativo.org) | Balance legislativo 2025 |
| INDEC | [indec.gob.ar](https://www.indec.gob.ar) | Proyecciones de población |

---

## 📖 Marco teórico

- Laakso, M. y Taagepera, R. (1979). *Effective Number of Parties*. Comparative Political Studies.
- Rae, D. W. (1967). *The Political Consequences of Electoral Laws*. Yale University Press.
- Mustapic, A. M. (2002). *Oscillating Relations: President and Congress in Argentina*. Cambridge University Press.
- IPU — Inter-Parliamentary Union (2022). *Parline Database on National Parliaments*.
- CPA-Zentralstelle (2019). *Benchmarking and Self-Assessment for Parliaments*.

---

## ⚠️ Aviso legal

Esta herramienta es de carácter experimental y académico. Los datos provienen de fuentes públicas oficiales del Estado argentino. Los resultados son indicadores algorítmicos — no implican juicio de valor, acusación ni determinación de responsabilidad sobre ninguna empresa, organismo o persona.

---

## 👤 Autor

**Ph.D. Vicente Humberto Monteverde**
Doctor en Ciencias Económicas · Investigador en economía política y fenómenos de corrupción.
Autor de la teoría de Transferencia Regresiva de Ingresos y desarrollador del algoritmo XAI aplicado al análisis de contrataciones públicas. Publicaciones en *Journal of Financial Crime* (Emerald Publishing).

✉️ vhmonte@retina.ar · viny01958@gmail.com

---

*Monitor Legislativo Senado v1.0 · Marzo 2026 · [github.com/Viny2030/monitor_legistativo_senadores](https://github.com/Viny2030/monitor_legistativo_senadores)*
