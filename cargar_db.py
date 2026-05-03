"""
cargar_db.py
Carga los CSVs generados por pipeline.py a la DB PostgreSQL de Railway.
Uso: python cargar_db.py
"""
import os
import sys
import glob
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import psycopg2
import psycopg2.extras

_raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL") or ""
DB_URL = _raw.replace("postgres://", "postgresql://", 1)

DATA_DIR = Path(__file__).parent / "data"


def conectar():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL no configurada")
    return psycopg2.connect(DB_URL)


def latest_csv(pattern):
    files = sorted(glob.glob(str(DATA_DIR / pattern)), reverse=True)
    return Path(files[0]) if files else None


def cargar_senadores(conn, csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig", on_bad_lines="skip")
    fecha = csv_path.stem.split("_")[-1]  # senadores_2026-05-03 → 2026-05-03
    cur = conn.cursor()

    # Borrar registros de esa fecha para evitar duplicados
    cur.execute("DELETE FROM senadores WHERE fecha_datos = %s", (fecha,))

    cols = [
        "id", "nombre", "provincia", "partido", "periodo_legal", "periodo_real",
        "reemplazo", "observaciones", "foto", "email", "telefono", "redes",
        "partido_normalizado", "rol_provincial", "abstenciones", "ausencias",
        "lev_vot", "votos_negativos", "no_emite", "votos_afirmativos",
        "votos_total", "participation_pct"
    ]

    inserted = 0
    for _, row in df.iterrows():
        def v(col):
            val = row.get(col)
            if pd.isna(val) if hasattr(val, '__class__') and val.__class__.__name__ in ('float',) else False:
                return None
            return val if str(val) not in ('nan', 'None', '') else None

        try:
            cur.execute("""
                INSERT INTO senadores (
                    id, nombre, provincia, partido, periodo_legal, periodo_real,
                    reemplazo, observaciones, foto, email, telefono, redes,
                    partido_normalizado, rol_provincial, abstenciones, ausencias,
                    lev_vot, votos_negativos, no_emite, votos_afirmativos,
                    votos_total, participation_pct, fecha_datos
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (nombre, fecha_datos) DO UPDATE SET
                    participation_pct = EXCLUDED.participation_pct,
                    votos_total = EXCLUDED.votos_total,
                    votos_afirmativos = EXCLUDED.votos_afirmativos,
                    votos_negativos = EXCLUDED.votos_negativos,
                    abstenciones = EXCLUDED.abstenciones,
                    ausencias = EXCLUDED.ausencias,
                    partido_normalizado = EXCLUDED.partido_normalizado,
                    rol_provincial = EXCLUDED.rol_provincial,
                    foto = EXCLUDED.foto,
                    email = EXCLUDED.email
            """, (
                v("id"), v("nombre"), v("provincia"), v("partido"),
                v("periodo_legal"), v("periodo_real"), v("reemplazo"),
                v("observaciones"), v("foto"), v("email"), v("telefono"), v("redes"),
                v("partido_normalizado"), v("rol_provincial"),
                v("abstenciones"), v("ausencias"), v("lev_vot"),
                v("votos_negativos"), v("no_emite"), v("votos_afirmativos"),
                v("votos_total"), v("participation_pct"), fecha
            ))
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  Error en {row.get('nombre')}: {e}")

    conn.commit()
    cur.close()
    print(f"  ✅ senadores: {inserted} filas → fecha {fecha}")
    return inserted


def cargar_reporte_partido(conn, csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig", on_bad_lines="skip")
    fecha = csv_path.stem.split("_")[-1]
    cur = conn.cursor()
    cur.execute("DELETE FROM reporte_partido WHERE fecha_datos = %s", (fecha,))

    inserted = 0
    for _, row in df.iterrows():
        def v(col):
            val = row.get(col)
            try:
                if pd.isna(val): return None
            except: pass
            return val if str(val) not in ('nan', 'None', '') else None

        try:
            cur.execute("""
                INSERT INTO reporte_partido (
                    partido, bancas, participation_pct,
                    votos_afirmativos, votos_negativos, abstenciones,
                    mayoria, primera_minoria, fecha_datos
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (partido, fecha_datos) DO UPDATE SET
                    bancas = EXCLUDED.bancas,
                    participation_pct = EXCLUDED.participation_pct,
                    votos_afirmativos = EXCLUDED.votos_afirmativos,
                    votos_negativos = EXCLUDED.votos_negativos
            """, (
                v("partido"), v("bancas"), v("participation_pct"),
                v("votos_afirmativos"), v("votos_negativos"), v("abstenciones"),
                v(chr(77)+"ayoría") or v("Mayoria") or v("mayoria"),
                v("Primera Minoría") or v("primera_minoria"),
                fecha
            ))
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  Error partido {row.get('partido')}: {e}")

    conn.commit()
    cur.close()
    print(f"  ✅ reporte_partido: {inserted} filas → fecha {fecha}")
    return inserted


def cargar_reporte_provincial(conn, csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig", on_bad_lines="skip")
    fecha = csv_path.stem.split("_")[-1]
    cur = conn.cursor()
    cur.execute("DELETE FROM reporte_provincial WHERE fecha_datos = %s", (fecha,))

    inserted = 0
    for _, row in df.iterrows():
        def v(col):
            val = row.get(col)
            try:
                if pd.isna(val): return None
            except: pass
            return val if str(val) not in ('nan', 'None', '') else None

        try:
            cur.execute("""
                INSERT INTO reporte_provincial (
                    provincia, senadores, participation_pct,
                    votos_total, partidos, mayoria, primera_minoria, fecha_datos
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (provincia, fecha_datos) DO UPDATE SET
                    participation_pct = EXCLUDED.participation_pct,
                    votos_total = EXCLUDED.votos_total,
                    partidos = EXCLUDED.partidos
            """, (
                v("provincia"), v("senadores"), v("participation_pct"),
                v("votos_total"), v("partidos"),
                v(chr(77)+"ayoría") or v("Mayoria") or v("mayoria"),
                v("Primera Minoría") or v("primera_minoria"),
                fecha
            ))
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  Error provincia {row.get('provincia')}: {e}")

    conn.commit()
    cur.close()
    print(f"  ✅ reporte_provincial: {inserted} filas → fecha {fecha}")
    return inserted


def main():
    print("=" * 55)
    print("📦 Cargando CSVs → PostgreSQL Railway")
    print(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 55)

    conn = conectar()
    print("✅ Conectado a DB\n")

    # Senadores
    csv = latest_csv("senadores_*.csv")
    if csv:
        print(f"📄 {csv.name}")
        cargar_senadores(conn, csv)
    else:
        print("❌ No se encontró CSV de senadores")

    # Partido
    csv = latest_csv("reporte_partido_senado_*.csv")
    if csv:
        print(f"📄 {csv.name}")
        cargar_reporte_partido(conn, csv)
    else:
        print("❌ No se encontró CSV de partidos")

    # Provincial
    csv = latest_csv("reporte_provincial_senado_*.csv")
    if csv:
        print(f"📄 {csv.name}")
        cargar_reporte_provincial(conn, csv)
    else:
        print("❌ No se encontró CSV provincial")

    conn.close()
    print("\n✅ Carga completa")


if __name__ == "__main__":
    main()