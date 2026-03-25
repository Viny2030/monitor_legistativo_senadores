"""
scripts/calendario.py  —  Monitor Legislativo SENADO
Verificador de días hábiles para GitHub Actions
================================================
El Senado sesiona en días hábiles; no tiene sentido correr el scraper
en fines de semana o feriados nacionales.

Uso standalone:
    python scripts/calendario.py

Uso desde otro script:
    from scripts.calendario import es_dia_habil, verificar_o_salir
    verificar_o_salir()   # hace sys.exit(0) si no es día hábil
"""

import sys
from datetime import datetime
import holidays


def es_dia_habil() -> tuple[bool, str]:
    """
    Retorna (True, motivo) si es día hábil en Argentina.
    Retorna (False, motivo) si es fin de semana o feriado.
    """
    hoy = datetime.now()

    # 1. ¿Es fin de semana?
    if hoy.weekday() >= 5:
        dia = "Sábado" if hoy.weekday() == 5 else "Domingo"
        return False, f"Fin de semana ({dia})"

    # 2. ¿Es feriado nacional argentino?
    ar_holidays = holidays.Argentina(years=hoy.year)
    if hoy in ar_holidays:
        return False, f"Feriado nacional ({ar_holidays.get(hoy)})"

    # 3. Período de receso legislativo: enero (el Senado no sesiona)
    if hoy.month == 1:
        return False, "Receso legislativo (enero)"

    return True, f"Día hábil — {hoy.strftime('%A %d/%m/%Y')}"


def verificar_o_salir():
    """
    Llama a es_dia_habil() e imprime el resultado.
    Si NO es día hábil hace sys.exit(0) (salida limpia para GitHub Actions).
    """
    debe_correr, motivo = es_dia_habil()
    print("=" * 55)
    print("🏛️  Monitor Senado — Verificador de Calendario")
    print("=" * 55)

    if not debe_correr:
        print(f"☕ Saltando ejecución: {motivo}")
        print("   Los datos del Senado no se actualizan hoy.")
        sys.exit(0)   # salida limpia → GitHub Actions marca el job como ✅

    print(f"✅ {motivo} — continuando ejecución...")


def main():
    verificar_o_salir()
    print("🚀 Proceso habilitado para correr.")


if __name__ == "__main__":
    main()
