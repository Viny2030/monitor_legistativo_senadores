"""
scripts/monitorear_dieta.py  --  Monitor Legislativo SENADO
Monitorea la Dieta y el Modulo legislativo del Senado
================================================================
Fuente principal (NUEVA, oficial y parseable):
  El Senado publica un recibo de sueldo real (anonimizado) en formato PDF:
    https://www.senado.gob.ar/prensa/adjunto/descargarArchivo/tipo/Dieta
  Ese PDF trae, en texto plano dentro del PDF:
    - El valor vigente del "modulo" (unidad de referencia salarial, ley 24.600)
    - DIETA (2.500 modulos, bruto y neto) -- pagina 1 "HABERES"
    - GASTOS DE REPRESENTACION (1.000 modulos) y DESARRAIGO (500 modulos),
      bruto y neto combinado -- pagina 2 "COMPLEMENTARIA"
  Todos estos montos son exactamente modulo x cantidad de modulos, es decir
  son datos reales y verificables, no estimaciones.

Antes este script scrapeaba texto libre en paginas HTML de senado.gob.ar que
cambiaron de estructura (institucional/retribuciones y institucional/
transparencia devuelven 404 hoy) y ya no publican un monto en pesos
parseable ahi. El PDF de arriba es la fuente estable que reemplaza eso.

Si detecta un valor de modulo distinto al guardado en dieta.json:
  1. Imprime alerta con variacion porcentual
  2. Actualiza dieta.json automaticamente (con --actualizar)
  3. Guarda historial en data/dieta_historial.csv

Uso:
  python scripts/monitorear_dieta.py            # solo consulta
  python scripts/monitorear_dieta.py --actualizar
"""

import sys
import re
import csv
import os
import json
import requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DIETA_JSON     = "dieta.json"
HISTORIAL_CSV  = "data/dieta_historial.csv"
HEADERS        = {"User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)"}

URL_RECIBO_PDF = "https://www.senado.gob.ar/prensa/adjunto/descargarArchivo/tipo/Dieta"

# Valor de modulo conocido -- ultimo recurso si el PDF no se puede leer
MODULO_HARDCODED = 2554.849933   # $/modulo, recibo ene.2026 -- actualizar si cambia mucho


# ── Cargar valor actual ───────────────────────────────────────────────────────

def cargar_dieta_actual() -> int:
    """
    Lee la dieta bruta (2.500 modulos) vigente desde dieta.json.
    Se mantiene por compatibilidad con quien ya usaba esta funcion
    (devuelve solo el bruto de la dieta base, no el paquete completo).
    """
    detalle = cargar_dieta_detalle()
    return detalle["dieta_base_bruto"]


def cargar_dieta_detalle() -> dict:
    """Lee el detalle completo (modulo + todos los montos) desde dieta.json."""
    if os.path.exists(DIETA_JSON):
        try:
            with open(DIETA_JSON, encoding="utf-8") as f:
                data = json.load(f)
            if float(data.get("valor_modulo", 0)) > 100:
                return data
        except Exception:
            pass
    return _detalle_desde_modulo(MODULO_HARDCODED, fuente="hardcoded")


def _detalle_desde_modulo(modulo: float, fuente: str, periodo: str = "") -> dict:
    """Deriva todos los montos bruto a partir del valor del modulo."""
    dieta_base_bruto = round(modulo * 2500, 2)
    gastos_bruto     = round(modulo * 1000, 2)
    desarraigo_bruto = round(modulo * 500, 2)
    return {
        "valor_modulo":        modulo,
        "dieta_base_bruto":    dieta_base_bruto,
        "dieta_base_neto":     None,   # se completa si el PDF trae el TOTAL NETO real
        "gastos_bruto":        gastos_bruto,
        "desarraigo_bruto":    desarraigo_bruto,
        "complementaria_neto": None,
        "bruto_con_aumento":   round(dieta_base_bruto + gastos_bruto + desarraigo_bruto, 2),
        "neto_con_aumento":    None,
        "periodo":             periodo,
        "fuente":              fuente,
    }


# ── Parseo de montos formato AR ("$ 6.387.124,83" -> 6387124.83) ─────────────

def _parse_monto_ar(txt: str) -> float:
    limpio = txt.strip().replace(".", "").replace(",", ".")
    return float(limpio)


# ── Descarga y parseo del recibo oficial (PDF) ───────────────────────────────

def obtener_detalle_desde_recibo() -> dict | None:
    """
    Descarga el recibo de sueldo oficial (PDF) desde senado.gob.ar y extrae:
      - valor del modulo
      - DIETA (2.500 mod.) bruto y neto -- pagina "HABERES"
      - GASTOS DE REPRESENTACION (1.000 mod.) y DESARRAIGO (500 mod.) brutos,
        y el neto combinado de ambos -- pagina "COMPLEMENTARIA"
    """
    try:
        import pdfplumber
    except ImportError:
        print("  ⚠️  Falta 'pdfplumber' (agregalo a requirements.txt). No se puede leer el PDF.")
        return None

    try:
        r = requests.get(URL_RECIBO_PDF, headers=HEADERS, timeout=20, verify=False)
        r.raise_for_status()
        if "pdf" not in r.headers.get("Content-Type", "").lower():
            print(f"  ⚠️  El recibo no vino como PDF (Content-Type: {r.headers.get('Content-Type')})")
            return None

        import io
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            if len(pdf.pages) < 1:
                return None
            texto_p1 = pdf.pages[0].extract_text() or ""
            texto_p2 = pdf.pages[1].extract_text() if len(pdf.pages) > 1 else ""

        m_modulo = re.search(r"VALOR DEL M[ÓO]DULO\s*\$\s*([\d.,]+)", texto_p1)
        m_periodo = re.search(r"MES DE\s+([A-ZÁÉÍÓÚ]+\s+\d{4})", texto_p1)
        m_dieta_bruto = re.search(r"\bDIETA\s+1[.,]00\s*\$\s*([\d.,]+)", texto_p1)
        m_dieta_neto  = re.search(r"TOTAL NETO\s*\$\s*\$?\s*([\d.,]+)", texto_p1)

        if not (m_modulo and m_dieta_bruto and m_dieta_neto):
            print("  ⚠️  No se pudieron leer todos los campos esperados en la página 1 del recibo.")
            return None

        modulo       = _parse_monto_ar(m_modulo.group(1))
        periodo      = m_periodo.group(1).title() if m_periodo else ""
        dieta_bruto  = _parse_monto_ar(m_dieta_bruto.group(1))
        dieta_neto   = _parse_monto_ar(m_dieta_neto.group(1))

        gastos_bruto = desarraigo_bruto = complementaria_neto = None
        if texto_p2:
            m_gastos = re.search(r"GASTOS DE REPRESENTACI[ÓO]N\s+1[.,]00\s*\$\s*([\d.,]+)", texto_p2)
            m_desarr = re.search(r"DESARRAIGO\s+1[.,]00\s*\$\s*([\d.,]+)", texto_p2)
            m_neto2  = re.search(r"TOTAL NETO\s*\$\s*\$?\s*([\d.,]+)", texto_p2)
            if m_gastos: gastos_bruto = _parse_monto_ar(m_gastos.group(1))
            if m_desarr: desarraigo_bruto = _parse_monto_ar(m_desarr.group(1))
            if m_neto2:  complementaria_neto = _parse_monto_ar(m_neto2.group(1))

        # Sanity check: el bruto de dieta debe ser ~2500 x modulo
        if not (2400 * modulo <= dieta_bruto <= 2600 * modulo):
            print(f"  ⚠️  DIETA leída (${dieta_bruto:,.2f}) no coincide con 2.500 x módulo "
                  f"(${modulo * 2500:,.2f}). Se descarta por seguridad.")
            return None

        detalle = {
            "valor_modulo":        modulo,
            "dieta_base_bruto":    dieta_bruto,
            "dieta_base_neto":     dieta_neto,
            "gastos_bruto":        gastos_bruto,
            "desarraigo_bruto":    desarraigo_bruto,
            "complementaria_neto": complementaria_neto,
            "periodo":             periodo,
            "fuente":              "senado.gob.ar (recibo oficial PDF)",
        }
        detalle["bruto_con_aumento"] = round(
            dieta_bruto + (gastos_bruto or 0) + (desarraigo_bruto or 0), 2
        )
        detalle["neto_con_aumento"] = (
            round(dieta_neto + complementaria_neto, 2)
            if complementaria_neto is not None else None
        )
        return detalle

    except Exception as e:
        print(f"  ⚠️  Error al leer el recibo oficial: {e}")
        return None


# ── Historial ─────────────────────────────────────────────────────────────────

def guardar_historial(detalle: dict, fuente: str):
    os.makedirs("data", exist_ok=True)
    existe = os.path.exists(HISTORIAL_CSV)
    with open(HISTORIAL_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["fecha", "valor_modulo", "dieta_base_bruto", "bruto_con_aumento", "fuente"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            detalle["valor_modulo"],
            detalle["dieta_base_bruto"],
            detalle.get("bruto_con_aumento", ""),
            fuente,
        ])


def actualizar_dieta_json(detalle: dict):
    detalle = dict(detalle)
    detalle["fecha_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(DIETA_JSON, "w", encoding="utf-8") as f:
        json.dump(detalle, f, ensure_ascii=False, indent=2)
    print(f"  ✅ dieta.json actualizado → módulo=${detalle['valor_modulo']:,.2f} "
          f"| dieta base bruto=${detalle['dieta_base_bruto']:,.2f}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    actualizar = "--actualizar" in sys.argv

    detalle_actual = cargar_dieta_detalle()

    print("=" * 55)
    print("🏛️  Monitor Senado — Monitor de Dieta Legislativa")
    print(f"   Módulo actual en dieta.json: ${detalle_actual['valor_modulo']:,.2f}")
    print("=" * 55)

    print(f"\n🔍 Descargando recibo oficial: {URL_RECIBO_PDF}")
    detalle_nuevo = obtener_detalle_desde_recibo()

    if detalle_nuevo is None:
        print("\n⚠️  No se pudo leer el recibo oficial esta vez.")
        print("   Se mantiene el último valor conocido en dieta.json (si existe).")
        sys.exit(1)

    modulo_actual = detalle_actual["valor_modulo"]
    modulo_nuevo  = detalle_nuevo["valor_modulo"]

    if abs(modulo_nuevo - modulo_actual) < 0.01:
        print(f"\n✅ Sin cambios. Módulo vigente: ${modulo_actual:,.2f} "
              f"({detalle_nuevo.get('periodo', '')})")
        guardar_historial(detalle_nuevo, "verificacion")
        if actualizar:
            actualizar_dieta_json(detalle_nuevo)   # refresca fecha/periodo igual
        sys.exit(0)

    variacion = (modulo_nuevo - modulo_actual) / modulo_actual * 100
    print(f"\n🔔 CAMBIO DETECTADO EN EL VALOR DEL MÓDULO:")
    print(f"   Anterior: ${modulo_actual:,.2f}")
    print(f"   Nuevo:    ${modulo_nuevo:,.2f}  ({detalle_nuevo.get('periodo', '')})")
    print(f"   Variación: {variacion:+.1f}%")

    guardar_historial(detalle_nuevo, "scraper_senado_pdf")

    if actualizar:
        actualizar_dieta_json(detalle_nuevo)
    else:
        print(f"\n  Para actualizar automáticamente:")
        print(f"  python scripts/monitorear_dieta.py --actualizar")
        sys.exit(2)


if __name__ == "__main__":
    main()
