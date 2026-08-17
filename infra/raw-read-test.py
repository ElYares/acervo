"""Cliente externo que lee la capa raw. Valida HU-002.

La costura que nunca se habia ejecutado: `ingest` deja parquet en s3://raw/ y
Spark escribe Iceberg via Nessie, pero Spark leyendo raw/ no se probo nunca.

Como connect-test.py, este script **no pasa ninguna configuracion de S3**. Si
tuviera que pasarla estaria probando su propia config y no la del servidor, que
es justo lo que hay que demostrar: el dia que dbt o Dagster lean raw/, no van a
traer credenciales.

  python raw-read-test.py [ruta] [sc://localhost:15002]
"""

import sys

from pyspark.sql import SparkSession

RUTA = "s3a://raw/tlc/yellow/2024-01.parquet"
REMOTE = "sc://localhost:15002"

# Las columnas que la historia exige ver tipadas. Se buscan por fragmento del
# nombre y no por nombre exacto a proposito: TLC cambio el esquema a lo largo de
# los anos y `tpep_pickup_datetime` no se llama igual en 2009 que en 2024.
EXIGIDAS = (
    ("recogida", "pickup", ("timestamp",)),
    ("bajada", "dropoff", ("timestamp",)),
    ("distancia", "distance", ("double", "float", "decimal")),
)


def main() -> int:
    ruta = sys.argv[1] if len(sys.argv) > 1 else RUTA
    remote = sys.argv[2] if len(sys.argv) > 2 else REMOTE

    print(f"conectando a {remote}")
    spark = SparkSession.builder.remote(remote).getOrCreate()
    print(f"OK  sesion establecida (server {spark.version})")

    print(f"== lectura de {ruta} ==")
    df = spark.read.parquet(ruta)
    print(f"OK  DataFrame construido, {len(df.columns)} columnas")

    filas = df.count()
    if filas <= 0:
        print(f"FALLO  el parquet devolvio {filas} filas", file=sys.stderr)
        return 1
    print(f"OK  {filas:,} filas")

    print("== esquema ==")
    campos = {c.name.lower(): c.dataType.simpleString() for c in df.schema.fields}
    for nombre, tipo in campos.items():
        print(f"    {nombre:<24} {tipo}")

    print("== columnas de viaje tipadas ==")
    fallos = []
    for etiqueta, fragmento, aceptados in EXIGIDAS:
        halladas = {n: t for n, t in campos.items() if fragmento in n}
        if not halladas:
            fallos.append(f"{etiqueta}: ninguna columna contiene '{fragmento}'")
            continue
        tipadas = {n: t for n, t in halladas.items() if t.startswith(aceptados)}
        if not tipadas:
            fallos.append(
                f"{etiqueta}: {halladas} no tiene ningun tipo de {aceptados}; "
                "leer todo como string significaria que el parquet perdio los tipos"
            )
            continue
        print(f"OK  {etiqueta}: {tipadas}")

    if fallos:
        for f in fallos:
            print(f"FALLO  {f}", file=sys.stderr)
        return 1

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
