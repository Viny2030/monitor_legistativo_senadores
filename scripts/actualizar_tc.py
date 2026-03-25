"""
scripts/actualizar_tc.py  —  Monitor Legislativo SENADO
Tipo de Cambio diario ARS/USD
================================
Fuentes en cascada (primera que responde gana):
  1. dolarapi.com     — BNA oficial
  2. bluelytics       — BNA oficial + blue
  3. argentinadatos   — BNA oficial
  4. BCRA API v2      — TC minorista referencia (variable 4)
  5. Fallback         — último tc.json guardado, o hardcoded

Output: tc.json en la raíz del proyecto
  {
    "oficial_venta": 1420.0,
    "oficial_compra": 1370.0,
    "blue_venta": 1435.0,
    "fuente": "bluelytics",
    "fecha": "2026-03-25",
    "hora": "08:00"
  }

Uso desde otros scripts:
    from scripts.actualizar_tc import cargar_tc
    tc = cargar_tc()   # → float (oficial_venta)
"""

import requests
import json
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
TC_JSON      = "tc.json"
TC_HARDCODED = 1420.0      # BNA venta 25/03/2026 — actualizar si pasa más de 1 semana
SSL_VERIFY   = False        # Servidores .gob.ar con cert chain incompleto en Windows

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {"User-Agent": "MonitorLegislativoSenadores/1.0 (github.com/Viny2030)"}


# ── Fuentes ───────────────────────────────────────────────────────────────────

def _desde_dolarapi() -> dict | None:
    try:
        r = requests.get(
            "https://dolarapi.com/v1/dolares/oficial",
            headers=HEADERS, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        data = r.json()
        venta = float(data.get("venta", 0))
        if venta > 500:
            return {
                "oficial_venta":  venta,
                "oficial_compra": float(data.get("compra", round(venta * 0.965, 2))),
                "blue_venta":     None,
                "fuente":         "dolarapi.com",
            }
    except Exception as e:
        print(f"  ⚠️  dolarapi: {e}")
    return None


def _desde_bluelytics() -> dict | None:
    try:
        r = requests.get(
            "https://api.bluelytics.com.ar/v2/latest",
            headers=HEADERS, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        data   = r.json()
        oficial = data.get("oficial", {})
        blue    = data.get("blue", {})
        venta   = float(oficial.get("value_sell", 0))
        if venta > 500:
            return {
                "oficial_venta":  venta,
                "oficial_compra": float(oficial.get("value_buy", round(venta * 0.965, 2))),
                "blue_venta":     float(blue.get("value_sell", 0)) or None,
                "fuente":         "bluelytics.com.ar",
            }
    except Exception as e:
        print(f"  ⚠️  bluelytics: {e}")
    return None


def _desde_argentinadatos() -> dict | None:
    try:
        r = requests.get(
            "https://argentinadatos.com/api/v1/cotizaciones/dolares/oficial",
            headers=HEADERS, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            data = data[-1]
        venta = float(data.get("venta", 0))
        if venta > 500:
            return {
                "oficial_venta":  venta,
                "oficial_compra": float(data.get("compra", round(venta * 0.965, 2))),
                "blue_venta":     None,
                "fuente":         "argentinadatos.com",
            }
    except Exception as e:
        print(f"  ⚠️  argentinadatos: {e}")
    return None


def _desde_bcra() -> dict | None:
    try:
        r = requests.get(
            "https://api.bcra.gob.ar/estadisticas/v2.0/principalesvariables",
            headers=HEADERS, timeout=10, verify=SSL_VERIFY
        )
        r.raise_for_status()
        for var in r.json().get("results", []):
            if var.get("idVariable") == 4:
                val = float(var.get("valor", 0))
                if val > 500:
                    return {
                        "oficial_venta":  val,
                        "oficial_compra": round(val * 0.965, 2),
                        "blue_venta":     None,
                        "fuente":         "BCRA API v2",
                    }
    except Exception as e:
        print(f"  ⚠️  BCRA: {e}")
    return None


# ── Cargar / guardar ──────────────────────────────────────────────────────────

def cargar_tc(campo: str = "oficial_venta") -> float:
    """
    Carga el TC desde tc.json. Si no existe, devuelve hardcoded.
    Uso:  from scripts.actualizar_tc import cargar_tc; tc = cargar_tc()
    """
    paths = [TC_JSON, os.path.join(os.path.dirname(__file__), "..", TC_JSON)]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                val = float(data.get(campo, 0))
                if val > 500:
                    fecha = data.get("fecha", "")
                    hoy   = datetime.now().strftime("%Y-%m-%d")
                    if fecha != hoy:
                        print(f"  ℹ️  TC de {fecha} (no es hoy). Usando igual: ${val:,.2f}")
                    return val
            except Exception:
                pass
    print(f"  ⚠️  tc.json no encontrado. Usando fallback: ${TC_HARDCODED:,.2f}")
    return TC_HARDCODED


def guardar_tc(data: dict) -> None:
    now          = datetime.now()
    data["fecha"] = now.strftime("%Y-%m-%d")
    data["hora"]  = now.strftime("%H:%M")

    paths_destino = [
        TC_JSON,
        os.path.join(os.path.dirname(__file__), "..", TC_JSON),
    ]
    for path in paths_destino:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 Guardado: {os.path.abspath(path)}")
            return
        except Exception as e:
            print(f"  ⚠️  No se pudo guardar en {path}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> dict:
    print("=" * 55)
    print("🏛️  Monitor Senado — Actualizando Tipo de Cambio")
    print("=" * 55)

    fuentes = [
        ("dolarapi.com",   _desde_dolarapi),
        ("bluelytics",     _desde_bluelytics),
        ("argentinadatos", _desde_argentinadatos),
        ("BCRA API v2",    _desde_bcra),
    ]

    resultado = None
    for nombre, fn in fuentes:
        print(f"\n🔍 Intentando {nombre}...")
        resultado = fn()
        if resultado:
            print(f"  ✅ OK → oficial venta: ${resultado['oficial_venta']:,.2f}")
            break

    if not resultado:
        # Fallback: último tc.json guardado
        paths = [TC_JSON, os.path.join(os.path.dirname(__file__), "..", TC_JSON)]
        for path in paths:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        old = json.load(f)
                    if float(old.get("oficial_venta", 0)) > 500:
                        print(f"\n  ℹ️  Todas las fuentes fallaron.")
                        print(f"      Usando último guardado ({old.get('fecha')}): ${old['oficial_venta']:,.2f}")
                        resultado = old
                        resultado["fuente"] = f"cache ({old.get('fecha', '?')})"
                        break
                except Exception:
                    pass

    if not resultado:
        print(f"\n  ⚠️  Todas las fuentes fallaron. Usando hardcoded: ${TC_HARDCODED:,.2f}")
        resultado = {
            "oficial_venta":  TC_HARDCODED,
            "oficial_compra": round(TC_HARDCODED * 0.965, 2),
            "blue_venta":     None,
            "fuente":         f"hardcoded ({TC_HARDCODED})",
        }

    guardar_tc(resultado)

    print(f"\n📊 Tipo de cambio actualizado:")
    print(f"   Oficial venta:  ${resultado['oficial_venta']:>10,.2f}")
    print(f"   Oficial compra: ${resultado['oficial_compra']:>10,.2f}")
    if resultado.get("blue_venta"):
        print(f"   Blue venta:     ${resultado['blue_venta']:>10,.2f}")
    print(f"   Fuente: {resultado['fuente']}")
    print(f"   Fecha:  {resultado.get('fecha','?')} {resultado.get('hora','')}")

    return resultado


if __name__ == "__main__":
    main()
