import os
import re
import pandas as pd
import psycopg2
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
DATA_DIR = Path(__file__).parent.parent / "data"

def extraer_fecha(nombre_archivo):
    match = re.search(r"(\d{4}-\d{2}-\d{2})", nombre_archivo)
    return match.group(1) if match else None

def cargar_senadores(conn):
    archivos = sorted(DATA_DIR.glob("senadores_*.csv"))
    cur = conn.cursor()
    for archivo in archivos:
        fecha = extraer_fecha(archivo.name)
        if not fecha:
            continue
        df = pd.read_csv(archivo)
        df.columns = df.columns.str.strip()
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO senadores VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (nombre, fecha_datos) DO NOTHING
            """, (
                row.get("id"), row.get("nombre"), row.get("provincia"), row.get("partido"),
                row.get("periodoLegal"), row.get("periodoReal"), row.get("reemplazo"),
                row.get("observaciones"), row.get("foto"), row.get("email"),
                row.get("telefono"), row.get("redes"), row.get("partido_normalizado"),
                row.get("rol_provincial"), row.get("abstenciones"), row.get("ausencias"),
                row.get("lev.vot."), row.get("votos_negativos"), row.get("no emite"),
                row.get("votos_afirmativos"), row.get("votos_total"),
                row.get("participation_pct"), fecha
            ))
        print(f"Senadores cargados: {archivo.name}")
    conn.commit()
    cur.close()

def cargar_reporte_partido(conn):
    archivos = sorted(DATA_DIR.glob("reporte_partido_senado_*.csv"))
    cur = conn.cursor()
    for archivo in archivos:
        fecha = extraer_fecha(archivo.name)
        if not fecha:
            continue
        df = pd.read_csv(archivo)
        df.columns = df.columns.str.strip()
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO reporte_partido VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (partido, fecha_datos) DO NOTHING
            """, (
                row.get("partido"), row.get("bancas"), row.get("participation_pct"),
                row.get("votos_afirmativos"), row.get("votos_negativos"),
                row.get("abstenciones"), row.get("Mayoría"), row.get("Primera Minoría"), fecha
            ))
        print(f"Reporte partido cargado: {archivo.name}")
    conn.commit()
    cur.close()

def cargar_reporte_provincial(conn):
    archivos = sorted(DATA_DIR.glob("reporte_provincial_senado_*.csv"))
    cur = conn.cursor()
    for archivo in archivos:
        fecha = extraer_fecha(archivo.name)
        if not fecha:
            continue
        df = pd.read_csv(archivo)
        df.columns = df.columns.str.strip()
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO reporte_provincial VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (provincia, fecha_datos) DO NOTHING
            """, (
                row.get("provincia"), row.get("senadores"), row.get("participation_pct"),
                row.get("votos_total"), row.get("partidos"),
                row.get("Mayoría"), row.get("Primera Minoría"), fecha
            ))
        print(f"Reporte provincial cargado: {archivo.name}")
    conn.commit()
    cur.close()

if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    cargar_senadores(conn)
    cargar_reporte_partido(conn)
    cargar_reporte_provincial(conn)
    conn.close()
    print("Carga completa.")