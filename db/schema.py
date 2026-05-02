import os
import psycopg2

_raw = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL") or ""
DATABASE_URL = _raw.replace("postgres://", "postgresql://", 1)

def crear_tablas():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS senadores (
            id TEXT,
            nombre TEXT,
            provincia TEXT,
            partido TEXT,
            periodo_legal TEXT,
            periodo_real TEXT,
            reemplazo TEXT,
            observaciones TEXT,
            foto TEXT,
            email TEXT,
            telefono TEXT,
            redes TEXT,
            partido_normalizado TEXT,
            rol_provincial TEXT,
            abstenciones FLOAT,
            ausencias FLOAT,
            lev_vot FLOAT,
            votos_negativos FLOAT,
            no_emite FLOAT,
            votos_afirmativos FLOAT,
            votos_total FLOAT,
            participation_pct FLOAT,
            fecha_datos DATE,
            PRIMARY KEY (nombre, fecha_datos)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reporte_partido (
            partido TEXT,
            bancas FLOAT,
            participation_pct FLOAT,
            votos_afirmativos FLOAT,
            votos_negativos FLOAT,
            abstenciones FLOAT,
            mayoria FLOAT,
            primera_minoria FLOAT,
            fecha_datos DATE,
            PRIMARY KEY (partido, fecha_datos)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reporte_provincial (
            provincia TEXT,
            senadores FLOAT,
            participation_pct FLOAT,
            votos_total FLOAT,
            partidos TEXT,
            mayoria FLOAT,
            primera_minoria FLOAT,
            fecha_datos DATE,
            PRIMARY KEY (provincia, fecha_datos)
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("Tablas creadas correctamente.")

if __name__ == "__main__":
    crear_tablas()