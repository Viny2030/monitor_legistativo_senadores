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
    datos esperados: dieta_bruta_con, dieta_neta_con, dieta_usd_con,
                     dieta_bruta_sin, dieta_neta_sin, dieta_usd_sin,
                     tc, leyes_fuente
    """
    bruto_con  = datos.get("dieta_bruta_con",  "$9.990.000")
    neto_con   = datos.get("dieta_neta_con",   "~$8.100.000")
    usd_con    = datos.get("dieta_usd_con",    "~USD 5.580")
    bruto_sin  = datos.get("dieta_bruta_sin",  "$9.500.000")
    neto_sin   = datos.get("dieta_neta_sin",   "~$7.800.000")
    usd_sin    = datos.get("dieta_usd_sin",    "~USD 5.380")
    tc         = datos.get("tc",               "~$1.450 ARS/USD")
    fuente     = datos.get("fuente",           "iProfesional, oct.2025")

    return f"""  <div class="panel">
    <h3>Dietas de senadores en dólares — 2025</h3>
    <table class="tbl">
      <thead><tr>
        <th>Concepto</th>
        <th class="num">ARS (bruto)</th>
        <th class="num">ARS (neto)</th>
        <th class="num">USD neto (TC {tc})</th>
      </tr></thead>
      <tbody>
        <tr class="highlight">
          <td>Senador con aumento (jul.2025)</td>
          <td class="num">{bruto_con}</td>
          <td class="num">{neto_con}</td>
          <td class="num"><strong>{usd_con}</strong></td>
        </tr>
        <tr>
          <td>Senador sin aumento (desacoplado)</td>
          <td class="num">{bruto_sin}</td>
          <td class="num">{neto_sin}</td>
          <td class="num">{usd_sin}</td>
        </tr>
        <tr>
          <td>Dieta base (2.500 módulos)</td>
          <td class="num">~$6.250.000</td>
          <td class="num">~$5.100.000</td>
          <td class="num">~USD 3.520</td>
        </tr>
        <tr>
          <td>Gastos representación (1.000 mód.)</td>
          <td class="num">~$2.500.000</td>
          <td class="num">—</td>
          <td class="num">~USD 1.720</td>
        </tr>
        <tr>
          <td>Desarraigo +100km CABA (500 mód.)</td>
          <td class="num">~$1.250.000</td>
          <td class="num">—</td>
          <td class="num">~USD 860</td>
        </tr>
        <tr>
          <td>Costo por sesión (72 sen.)</td>
          <td class="num">~$611.800.000</td>
          <td class="num">—</td>
          <td class="num">~USD 421.900</td>
        </tr>
      </tbody>
    </table>
    <p class="nota-fuente">Fuente: {fuente}. TC {tc} (TC oficial jul.2025).</p>
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

if __name__ == "__main__":
    # Ejemplo de uso con datos del scraper.
    # En producción estos dicts los arma pipeline_senado.py con datos reales.
    datos_kpi_ejemplo = {
        "presupuesto_usd": "USD 94M",
        "crc_usd":         "USD 2,0",
        "dieta_usd":       "USD 5.500",
        "bancas":          72,
        "nep":             "5,06",
        "leyes_2025":      13,
        "subtitulo_leyes": "mínimo histórico",
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
        "arg_dieta_mes": 5580,
    }

    actualizar_comparativa(
        datos_kpi=datos_kpi_ejemplo,
        datos_leyes=datos_leyes_ejemplo,
        datos_paises=datos_paises_ejemplo,
    )