"""
scripts/monitorear_dieta.py  —  Monitor Legislativo SENADO
Monitorea cambios en la Dieta y el Módulo legislativo del Senado
================================================================
A diferencia de HCDN (que usa "módulo"), el Senado publica
la "dieta" y los viáticos en su sección de transparencia.

Fuentes:
  - senado.gob.ar/institucional/retribuciones (scraping)
  - presupuestoabierto.gob.ar (API con token — Jurisdicción 01/Senado)

Si detecta un valor diferente al actual en dieta.json:
  1. Imprime alerta con variación porcentual
  2. Actualiza dieta.json automáticamente
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
from bs4 import BeautifulSoup
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DIETA_JSON     = "dieta.json"
HISTORIAL_CSV  = "data/dieta_historial.csv"
HEADERS        = {"User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)"}

URLS_DIETA = [
    "https://www.senado.gob.ar/institucional/retribuciones",
    "https://www.senado.gob.ar/institucional/transparencia",
    "https://www.senado.gob.ar/micrositios/DatosAbiertos/",
]

# Valor de dieta conocido — actualizar si cambia
DIETA_HARDCODED = 3_500_000   # ARS aprox. 2026 (referencia)


# ── Cargar valor actual ───────────────────────────────────────────────────────

def cargar_dieta_actual() -> int:
    """Lee el valor vigente desde dieta.json. Si no existe usa el hardcoded."""
    if os.path.exists(DIETA_JSON):
        try:
            with open(DIETA_JSON, encoding="utf-8") as f:
                data = json.load(f)
            val = int(data.get("dieta_mensual", 0))
            if val > 100_000:
                return val
        except Exception:
            pass
    return DIETA_HARDCODED


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_dieta() -> int | None:
    """Busca el valor de la dieta en el sitio oficial del Senado."""
    for url in URLS_DIETA:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            texto = soup.get_text(separator=" ")

            patrones = [
                r'dieta[^\d]{0,30}([\d]{1,3}[\.\,][\d]{3}[\.\,][\d]{3})',  # 3.500.000
                r'dieta[^\d]{0,30}\$\s*([\d]{1,3}[\.\,][\d]{3})',            # $3.500
                r'\$\s*([\d]{1,3}[\.\,][\d]{3}[\.\,][\d]{3})',               # $3.500.000
                r'([\d]{1,3}[\.\,][\d]{3}[\.\,][\d]{3})\s*(?:pesos|ars)',   # 3.500.000 pesos
            ]

            for patron in patrones:
                matches = re.findall(patron, texto, re.IGNORECASE)
                if matches:
                    val_str = matches[0].replace(".", "").replace(",", "")
                    val = int(val_str)
                    if 500_000 <= val <= 50_000_000:   # rango razonable dieta senadores
                        print(f"  ✓ Dieta encontrada en {url}: ${val:,}")
                        return val

            print(f"  ⚠️  No se encontró valor en {url}")

        except Exception as e:
            print(f"  ⚠️  Error al consultar {url}: {e}")

    return None


# ── Historial ─────────────────────────────────────────────────────────────────

def guardar_historial(valor: int, fuente: str):
    os.makedirs("data", exist_ok=True)
    existe = os.path.exists(HISTORIAL_CSV)
    with open(HISTORIAL_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["fecha", "dieta_mensual", "fuente"])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), valor, fuente])


def actualizar_dieta_json(nuevo_valor: int, datos_extra: dict = None):
    """Guarda el nuevo valor en dieta.json."""
    data = {
        "dieta_mensual": nuevo_valor,
        "fecha_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fuente": "scraping senado.gob.ar",
    }
    if datos_extra:
        data.update(datos_extra)

    with open(DIETA_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ dieta.json actualizado → dieta_mensual = ${nuevo_valor:,}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    actualizar = "--actualizar" in sys.argv

    dieta_actual = cargar_dieta_actual()

    print("=" * 55)
    print("🏛️  Monitor Senado — Monitor de Dieta Legislativa")
    print(f"   Valor actual en dieta.json: ${dieta_actual:,}")
    print("=" * 55)

    print("\n🔍 Consultando sitio del Senado...")
    dieta_nueva = scrape_dieta()

    if dieta_nueva is None:
        print("\n⚠️  No se pudo obtener el valor de la dieta.")
        print("   Verificar manualmente: https://www.senado.gob.ar/institucional/retribuciones")
        sys.exit(1)

    if dieta_nueva == dieta_actual:
        print(f"\n✅ Sin cambios. Dieta vigente: ${dieta_actual:,}")
        guardar_historial(dieta_nueva, "verificacion")
        sys.exit(0)

    # ── CAMBIO DETECTADO ──────────────────────────────────────────────────────
    variacion = (dieta_nueva - dieta_actual) / dieta_actual * 100
    print(f"\n🔔 CAMBIO DETECTADO EN LA DIETA:")
    print(f"   Anterior: ${dieta_actual:,}")
    print(f"   Nueva:    ${dieta_nueva:,}")
    print(f"   Variación: {variacion:+.1f}%")

    guardar_historial(dieta_nueva, "scraper_senado")

    if actualizar:
        actualizar_dieta_json(dieta_nueva)
    else:
        print(f"\n  Para actualizar automáticamente:")
        print(f"  python scripts/monitorear_dieta.py --actualizar")
        sys.exit(2)   # código 2 → el pipeline puede detectar el cambio


if __name__ == "__main__":
    main()
