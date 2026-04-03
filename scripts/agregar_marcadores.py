"""Agrega marcadores a indicadores_bloques_senadores.html y nomina_detalle_senadores.html"""
import sys

ULTIMO = '{nombre:"Zamora, Gerardo",provincia:"SANTIAGO DEL ESTERO",bloque:"FRENTE CÍVICO POR SANTIAGO"}\n];'

archivos = [
    ("dashboard/indicadores_bloques_senadores.html", "// BLOQUES:START", "// BLOQUES:END"),
    ("dashboard/nomina_detalle_senadores.html",      "// NOMINA:START",  "// NOMINA:END"),
]

for path, start, end in archivos:
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()

        if start in txt:
            print(f"✅ {path} ya tiene marcadores")
            continue

        # Buscar const SENADORES=[ o const SENADORES = [
        for patron in ["const SENADORES=[\n", "const SENADORES = [\n"]:
            if patron in txt:
                txt = txt.replace(patron, f"{start}\n// Actualizado automáticamente — no editar a mano\n{patron}")
                break
        else:
            print(f"⚠️  No encontré 'const SENADORES' en {path}")
            continue

        if ULTIMO in txt:
            txt = txt.replace(ULTIMO, ULTIMO + f"\n{end}")
        else:
            print(f"⚠️  No encontré el cierre del array en {path}")
            continue

        with open(path, "w", encoding="utf-8") as f:
            f.write(txt)
        print(f"✅ Marcadores agregados en {path}")

    except FileNotFoundError:
        print(f"⚠️  No existe: {path}")