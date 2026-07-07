#!/usr/bin/env python3
"""
actualizar_comparativa_senado.py
Actualiza dashboard/comparativa_senado.html con datos del scraper.
Patron identico al resto de scripts del repo (marker-based replacement).
Solo reemplaza contenido entre marcadores — NO modifica nada fuera de ellos.
"""

import re
import sys
from pathlib import Path
from datetime import datetime

# ── Rutas ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
HTML_PATH = BASE_DIR / "dashboard" / "comparativa_senado.html"

# ── Helpers ────────────────────────────────────────────────────────────────

def leer_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def escribir_html(path: Path, contenido: str) -> None:
    path.write_text(contenido, encoding="utf-8")

def reemplazar_bloque(html: str, marcador: str, nuevo_contenido: str) -> str:
    """
    Reemplaza el contenido entre marcadores START/END.
    Soporta tanto <!-- MARCADOR:START --> (HTML) como // MARCADOR:START (JS).
    """
    # Intentar primero con comentarios HTML
    patron = re.compile(
        r"(<!-- " + re.escape(marcador) + r":START -->)"
        r".*?"
        r"(<!-- " + re.escape(marcador) + r":END -->)",
        re.DOTALL
    )
    if patron.search(html):
        return patron.sub(r"\g<1>\n" + nuevo_contenido + r"\n\g<2>", html)

    # Intentar con comentarios JS (//)
    patron_js = re.compile(
        r"(// " + re.escape(marcador) + r":START)"
        r".*?"
        r"(// " + re.escape(marcador) + r":END)",
        re.DOTALL
    )
    if patron_js.search(html):
        return patron_js.sub(r"\g<1>\n" + nuevo_contenido + r"\n\g<2>", html)

    print(f"  [WARN] Marcador '{marcador}' no encontrado en el HTML.")
    return html

# ── Generadores de bloques HTML ────────────────────────────────────────────

def generar_kpi_comparativa(datos: dict) -> str:
    """
    Genera la barra de KPIs resumen de la comparativa.
    datos esperados: presupuesto_usd, crc_usd, dieta_usd, bancas, nep, leyes_2025
    """
    presupuesto = datos.get("presupuesto_usd", "USD 94M")
    crc         = datos.get("crc_usd", "USD 2,0")
    dieta       = datos.get("dieta_usd", "USD 5.500")
    bancas      = datos.get("bancas", 72)
    nep         = datos.get("nep", "5,06")
    leyes       = datos.get("leyes_2025", 13)
    subtitulo_leyes = datos.get("subtitulo_leyes", "mínimo histórico")

    return f"""<div class="kpi-bar">
  <div class="kpi-card"><div class="kv">{presupuesto}</div><div class="kl">Presupuesto Senado</div><div class="ks">estimado 2025 (TC oficial)</div></div>
  <div class="kpi-card"><div class="kv">{crc}</div><div class="kl">CRC en dólares</div><div class="ks">por habitante / año</div></div>
  <div class="kpi-card"><div class="kv">{dieta}</div><div class="kl">Dieta neta senador</div><div class="ks">promedio jul.2025</div></div>
  <div class="kpi-card"><div class="kv">{bancas}</div><div class="kl">Bancas</div><div class="ks">3 por provincia</div></div>
  <div class="kpi-card"><div class="kv">{nep}</div><div class="kl">NEP</div><div class="ks">Laakso-Taagepera</div></div>
  <div class="kpi-card"><div class="kv">{leyes}</div><div class="kl">Leyes 2025</div><div class="ks">{subtitulo_leyes}</div></div>
</div>"""


def generar_dietas_usd(datos: dict) -> str:
    """
    Genera la tabla de dietas en dólares.
    datos esperados (todos derivados del recibo oficial PDF + TC real, ver
    scripts/monitorear_dieta.py y scripts/actualizar_tc.py):
      dieta_bruta_con, dieta_neta_con, dieta_usd_con   → paquete completo (2500+1000+500 módulos)
      dieta_base_bruto, dieta_base_neto, dieta_base_usd → solo dieta (2500 módulos)
      gastos_bruto, gastos_usd                          → gastos de representación (1000 módulos)
      desarraigo_bruto, desarraigo_usd                  → desarraigo (500 módulos)
      tc, fuente, periodo
    Las filas "sin aumento" (senadores desacoplados del ajuste automático) y
    "costo por sesión" NO tienen fuente pública parseable identificada todavía
    — quedan como referencia manual, marcadas explícitamente como tal.
    """
    bruto_con  = datos.get("dieta_bruta_con",  "$9.990.000")
    neto_con   = datos.get("dieta_neta_con",   "~$8.100.000")
    usd_con    = datos.get("dieta_usd_con",    "~USD 5.580")
    bruto_sin  = datos.get("dieta_bruta_sin",  "$9.500.000")
    neto_sin   = datos.get("dieta_neta_sin",   "~$7.800.000")
    usd_sin    = datos.get("dieta_usd_sin",    "~USD 5.380")

    base_bruto = datos.get("dieta_base_bruto", "~$6.250.000")
    base_neto  = datos.get("dieta_base_neto",  "~$5.100.000")
    base_usd   = datos.get("dieta_base_usd",   "~USD 3.520")

    gastos_bruto = datos.get("gastos_bruto", "~$2.500.000")
    gastos_usd   = datos.get("gastos_usd",   "~USD 1.720")

    desarraigo_bruto = datos.get("desarraigo_bruto", "~$1.250.000")
    desarraigo_usd    = datos.get("desarraigo_usd",   "~USD 860")

    tc      = datos.get("tc",      "~$1.450 ARS/USD")
    fuente  = datos.get("fuente",  "iProfesional, oct.2025")
    periodo = datos.get("periodo", "")

    return f"""  <div class="panel">
    <h3>Dietas de senadores en dólares{f' — {periodo}' if periodo else ' — 2025'}</h3>
    <table class="tbl">
      <thead><tr>
        <th>Concepto</th>
        <th class="num">ARS (bruto)</th>
        <th class="num">ARS (neto)</th>
        <th class="num">USD neto (TC {tc})</th>
      </tr></thead>
      <tbody>
        <tr class="highlight">
          <td>Senador con aumento{f' ({periodo})' if periodo else ''}</td>
          <td class="num">{bruto_con}</td>
          <td class="num">{neto_con}</td>
          <td class="num"><strong>{usd_con}</strong></td>
        </tr>
        <tr>
          <td>Senador sin aumento (desacoplado) <span title="Sin fuente pública parseable — referencia manual">*</span></td>
          <td class="num">{bruto_sin}</td>
          <td class="num">{neto_sin}</td>
          <td class="num">{usd_sin}</td>
        </tr>
        <tr>
          <td>Dieta base (2.500 módulos)</td>
          <td class="num">{base_bruto}</td>
          <td class="num">{base_neto}</td>
          <td class="num">{base_usd}</td>
        </tr>
        <tr>
          <td>Gastos representación (1.000 mód.)</td>
          <td class="num">{gastos_bruto}</td>
          <td class="num">—</td>
          <td class="num">{gastos_usd}</td>
        </tr>
        <tr>
          <td>Desarraigo +100km CABA (500 mód.)</td>
          <td class="num">{desarraigo_bruto}</td>
          <td class="num">—</td>
          <td class="num">{desarraigo_usd}</td>
        </tr>
        <tr>
          <td>Costo por sesión (72 sen.) <span title="Sin fuente pública parseable — referencia manual">*</span></td>
          <td class="num">~$611.800.000</td>
          <td class="num">—</td>
          <td class="num">~USD 421.900</td>
        </tr>
      </tbody>
    </table>
    <p class="nota-fuente">Fuente: {fuente}. TC {tc}. <span title="Sin fuente pública parseable">*</span> = referencia manual, no automatizada.</p>
  </div>"""


def generar_leyes_sesiones(datos: dict) -> str:
    """
    Genera los dos paneles de leyes sancionadas y sesiones realizadas.
    datos esperados: leyes_2024_arg, leyes_2025_arg, sesiones_arg
    """
    leyes_2024 = datos.get("leyes_2024_arg", "~38")
    leyes_2025 = datos.get("leyes_2025_arg", "13")
    sesiones   = datos.get("sesiones_arg",   "12")

    return f"""    <div class="panel">
      <h3>Leyes sancionadas por año (Senado / Cámara Alta)</h3>
      <table class="tbl">
        <thead><tr>
          <th>País</th>
          <th class="num">Leyes 2024</th>
          <th class="num">Leyes 2025</th>
          <th>Tendencia</th>
        </tr></thead>
        <tbody>
          <tr class="highlight">
            <td>🇦🇷 Argentina (total bicameral)</td>
            <td class="num">~{leyes_2024}</td>
            <td class="num"><strong>{leyes_2025}</strong></td>
            <td><span class="pill" style="background:#dc2626">↓ Mínimo histórico</span></td>
          </tr>
          <tr>
            <td>🇧🇷 Brasil</td>
            <td class="num">~180</td>
            <td class="num">~160</td>
            <td><span class="pill" style="background:#d97706">→ Estable</span></td>
          </tr>
          <tr>
            <td>🇨🇱 Chile</td>
            <td class="num">116</td>
            <td class="num">~110</td>
            <td><span class="pill" style="background:#16a34a">↑ Alta productividad</span></td>
          </tr>
          <tr>
            <td>🇺🇾 Uruguay</td>
            <td class="num">~80</td>
            <td class="num">~85</td>
            <td><span class="pill" style="background:#16a34a">↑ Estable-alta</span></td>
          </tr>
          <tr>
            <td>🇲🇽 México</td>
            <td class="num">~200</td>
            <td class="num">~180</td>
            <td><span class="pill" style="background:#d97706">→ Estable</span></td>
          </tr>
          <tr>
            <td>🇪🇸 España</td>
            <td class="num">~90</td>
            <td class="num">~85</td>
            <td><span class="pill" style="background:#d97706">→ Moderada</span></td>
          </tr>
        </tbody>
      </table>
      <p class="nota-fuente">Fuentes: Congreso.ar, Senado Chile (Cuenta Pública 2024-2025), IPU Parline. Argentina: {leyes_2025} leyes bicamerales totales 2025.</p>
    </div>

    <div class="panel">
      <h3>Sesiones realizadas 2025</h3>
      <table class="tbl">
        <thead><tr>
          <th>País</th>
          <th class="num">Sesiones</th>
          <th class="num">Asistencia</th>
        </tr></thead>
        <tbody>
          <tr class="highlight">
            <td>🇦🇷 Argentina Senado</td>
            <td class="num"><strong>{sesiones}</strong></td>
            <td class="num"><strong>100%</strong></td>
          </tr>
          <tr>
            <td>🇦🇷 Argentina Diputados</td>
            <td class="num">16</td>
            <td class="num">~85%</td>
          </tr>
          <tr>
            <td>🇨🇱 Chile Senado</td>
            <td class="num">106</td>
            <td class="num">~90%</td>
          </tr>
          <tr>
            <td>🇺🇾 Uruguay Senado</td>
            <td class="num">~90</td>
            <td class="num">~88%</td>
          </tr>
          <tr>
            <td>🇪🇸 España Senado</td>
            <td class="num">~45</td>
            <td class="num">~82%</td>
          </tr>
          <tr>
            <td>🌐 OCDE promedio</td>
            <td class="num">~70</td>
            <td class="num">~85%</td>
          </tr>
        </tbody>
      </table>
      <p class="nota-fuente">Argentina Senado: {sesiones} sesiones (7 ord. + 5 esp.). Asistencia 100% en votaciones nominales verificadas (actas HSN). Chile: Cuenta Pública jul.2024–jun.2025.</p>
    </div>"""


def generar_paises_data(datos: dict) -> str:
    """
    Genera el array JS PAISES con los datos actualizados de Argentina.
    Solo se actualiza la fila de Argentina; el resto permanece hardcoded.
    datos esperados: arg_hab_sen, arg_nep, arg_costo_hab, arg_dieta_mes
    """
    arg_hab_sen   = datos.get("arg_hab_sen",   652000)
    arg_nep       = datos.get("arg_nep",       5.06)
    arg_costo_hab = datos.get("arg_costo_hab", 1.99)
    arg_dieta_mes = datos.get("arg_dieta_mes", 5580)

    return f"""var PAISES = [
  {{nombre:'🇦🇷 Argentina', hab_sen:{arg_hab_sen}, nep:{arg_nep}, costo_hab:{arg_costo_hab}, dieta_mes:{arg_dieta_mes}, color:'#C9A84C', highlight:true}},
  {{nombre:'🇧🇷 Brasil',    hab_sen:2630000, nep:3.8, costo_hab:2.80, dieta_mes:8000, color:'#16a34a'}},
  {{nombre:'🇨🇱 Chile',     hab_sen:390000,  nep:4.2, costo_hab:3.10, dieta_mes:4900, color:'#dc2626'}},
  {{nombre:'🇺🇾 Uruguay',   hab_sen:117000,  nep:3.5, costo_hab:4.50, dieta_mes:4500, color:'#2563eb'}},
  {{nombre:'🇲🇽 México',    hab_sen:1050000, nep:3.2, costo_hab:1.20, dieta_mes:8700, color:'#7c3aed'}},
  {{nombre:'🇪🇸 España',    hab_sen:176000,  nep:4.8, costo_hab:5.80, dieta_mes:4000, color:'#d97706'}},
  {{nombre:'🌐 OCDE prom.', hab_sen:500000,  nep:3.9, costo_hab:8.50, dieta_mes:7900, color:'#64748b'}},
];"""


# ── Función principal ──────────────────────────────────────────────────────

def actualizar_comparativa(datos_kpi: dict = None,
                            datos_dietas: dict = None,
                            datos_leyes: dict = None,
                            datos_paises: dict = None) -> None:
    """
    Lee el HTML, aplica los reemplazos en los marcadores y escribe el resultado.
    Cada bloque es opcional: si no se pasan datos se usan los defaults (hardcoded actuales).
    """
    if not HTML_PATH.exists():
        print(f"[ERROR] No se encontró: {HTML_PATH}")
        sys.exit(1)

    print(f"[INFO] Leyendo {HTML_PATH}")
    html = leer_html(HTML_PATH)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # KPI_COMPARATIVA
    if datos_kpi:
        print("  → Actualizando KPI_COMPARATIVA")
        html = reemplazar_bloque(html, "KPI_COMPARATIVA", generar_kpi_comparativa(datos_kpi))

    # DIETAS_USD
    if datos_dietas:
        print("  → Actualizando DIETAS_USD")
        html = reemplazar_bloque(html, "DIETAS_USD", generar_dietas_usd(datos_dietas))

    # LEYES_SESIONES
    if datos_leyes:
        print("  → Actualizando LEYES_SESIONES")
        html = reemplazar_bloque(html, "LEYES_SESIONES", generar_leyes_sesiones(datos_leyes))

    # PAISES_DATA (array JS)
    if datos_paises:
        print("  → Actualizando PAISES_DATA")
        html = reemplazar_bloque(html, "PAISES_DATA", generar_paises_data(datos_paises))

    escribir_html(HTML_PATH, html)
    print(f"[OK] {HTML_PATH.name} actualizado — {timestamp}")


# ── Entry point ────────────────────────────────────────────────────────────

# Dieta "sin aumento" (senadores desacoplados del ajuste automático) y "costo
# por sesión": no hay fuente pública parseable identificada todavía para estos
# dos casos puntuales -- quedan como referencia manual (ver aviso "*" en la
# tabla generada). Todo lo demás en esta tabla sale del recibo oficial real
# (scripts/monitorear_dieta.py, PDF de senado.gob.ar) + TC real (BCRA/dolarapi).
DIETA_SIN_AUMENTO_BRUTO = 9_500_000
DIETA_SIN_AUMENTO_NETO  = 7_800_000

def _fmt_ars(v) -> str:
    return f"${v:,.0f}".replace(",", ".")

def _fmt_usd(v) -> str:
    return f"USD {v:,.0f}".replace(",", ".")

if __name__ == "__main__":
    # Tipo de cambio real — cascada dolarapi → bluelytics → argentinadatos
    # → BCRA API v4 → último tc.json guardado → hardcoded (ver actualizar_tc.py).
    try:
        from actualizar_tc import cargar_tc
        tc_actual = cargar_tc()
    except Exception as e:
        print(f"[WARN] No se pudo cargar TC real ({e}); usando referencia 1420.0")
        tc_actual = 1420.0

    # Dieta real (módulo + montos) desde el recibo oficial en PDF.
    try:
        from monitorear_dieta import cargar_dieta_detalle
        dieta = cargar_dieta_detalle()
    except Exception as e:
        print(f"[WARN] No se pudo cargar dieta real ({e}); usando referencia estática")
        dieta = {
            "dieta_base_bruto": 6_250_000, "dieta_base_neto": 5_100_000,
            "gastos_bruto": 2_500_000, "desarraigo_bruto": 1_250_000,
            "bruto_con_aumento": 9_990_000, "neto_con_aumento": 8_100_000,
            "periodo": "", "fuente": "referencia estática",
        }

    tc_fmt = f"${tc_actual:,.0f} ARS/USD".replace(",", ".")

    bruto_con = dieta["bruto_con_aumento"]
    neto_con  = dieta.get("neto_con_aumento") or DIETA_SIN_AUMENTO_NETO
    usd_con   = round(neto_con / tc_actual)

    base_bruto = dieta["dieta_base_bruto"]
    base_neto  = dieta.get("dieta_base_neto") or base_bruto
    base_usd   = round(base_neto / tc_actual)

    gastos_bruto     = dieta.get("gastos_bruto")
    desarraigo_bruto = dieta.get("desarraigo_bruto")
    gastos_usd       = round(gastos_bruto / tc_actual) if gastos_bruto else None
    desarraigo_usd   = round(desarraigo_bruto / tc_actual) if desarraigo_bruto else None

    dieta_usd_fmt = _fmt_usd(usd_con)

    datos_kpi_ejemplo = {
        "presupuesto_usd": "USD 94M",        # sin scraper propio aún — referencia manual
        "crc_usd":         "USD 2,0",        # requiere dato de población — referencia manual
        "dieta_usd":       dieta_usd_fmt,    # ← módulo real (PDF) + TC real
        "bancas":          72,
        "nep":             "5,06",
        "leyes_2025":      13,               # sin scraper de leyes sancionadas aún — referencia manual
        "subtitulo_leyes": "mínimo histórico",
    }
    datos_dietas_ejemplo = {
        "dieta_bruta_con": _fmt_ars(bruto_con),
        "dieta_neta_con":  f"~{_fmt_ars(neto_con)}",
        "dieta_usd_con":   f"~{dieta_usd_fmt}",
        "dieta_bruta_sin": _fmt_ars(DIETA_SIN_AUMENTO_BRUTO),
        "dieta_neta_sin":  f"~{_fmt_ars(DIETA_SIN_AUMENTO_NETO)}",
        "dieta_usd_sin":   f"~{_fmt_usd(round(DIETA_SIN_AUMENTO_NETO / tc_actual))}",
        "dieta_base_bruto": _fmt_ars(base_bruto),
        "dieta_base_neto":  f"~{_fmt_ars(base_neto)}",
        "dieta_base_usd":   f"~{_fmt_usd(base_usd)}",
        "gastos_bruto":     _fmt_ars(gastos_bruto) if gastos_bruto else "~$2.500.000",
        "gastos_usd":       f"~{_fmt_usd(gastos_usd)}" if gastos_usd else "~USD 1.720",
        "desarraigo_bruto": _fmt_ars(desarraigo_bruto) if desarraigo_bruto else "~$1.250.000",
        "desarraigo_usd":   f"~{_fmt_usd(desarraigo_usd)}" if desarraigo_usd else "~USD 860",
        "tc":              tc_fmt,
        "fuente":          f"{dieta.get('fuente', 'referencia')} (ARS) + TC en vivo (BCRA/dolarapi)",
        "periodo":         dieta.get("periodo", ""),
    }
    datos_leyes_ejemplo = {
        "leyes_2024_arg": "38",
        "leyes_2025_arg": "13",
        "sesiones_arg":   "12",
    }
    datos_paises_ejemplo = {
        "arg_hab_sen":   652000,
        "arg_nep":       5.06,
        "arg_costo_hab": 1.99,
        "arg_dieta_mes": usd_con,   # ← también calculado con dieta y TC reales
    }

    actualizar_comparativa(
        datos_kpi=datos_kpi_ejemplo,
        datos_dietas=datos_dietas_ejemplo,
        datos_leyes=datos_leyes_ejemplo,
        datos_paises=datos_paises_ejemplo,
    )