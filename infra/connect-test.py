"""Cliente externo de Spark Connect. Valida HU-001.

Lo que esta prueba demuestra y smoke-test.sh no: que la configuracion de
catalogo que vive en el SERVIDOR sirve. Por eso este script no pasa ni un solo
`spark.sql.catalog.*` — si tuviera que pasarlo, estaria probando su propia
configuracion, no la del servidor, y no demostraria nada nuevo.

  python connect-test.py [sc://localhost:15002]
"""

import sys

from pyspark.sql import SparkSession

REMOTE = sys.argv[1] if len(sys.argv) > 1 else "sc://localhost:15002"
TABLA = "acervo.smoke_connect.t"


def main() -> int:
    print(f"conectando a {REMOTE}")

    # Sin .config() de catalogo a proposito. Todo tiene que venir del servidor.
    spark = SparkSession.builder.remote(REMOTE).getOrCreate()
    print(f"OK  sesion establecida (server {spark.version})")

    ns = spark.sql("SHOW NAMESPACES IN acervo").collect()
    print(f"OK  el catalogo 'acervo' responde ({len(ns)} namespaces)")

    spark.sql("CREATE NAMESPACE IF NOT EXISTS acervo.smoke_connect")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {TABLA} (id BIGINT, nota STRING) USING iceberg")
    spark.sql(f"INSERT INTO {TABLA} VALUES (1, 'connect vivo')")

    filas = spark.sql(f"SELECT * FROM {TABLA}").collect()
    if len(filas) != 1 or filas[0]["nota"] != "connect vivo":
        print(f"FALLO  se esperaba 1 fila 'connect vivo', llegaron {filas}", file=sys.stderr)
        return 1
    print("OK  escritura y lectura Iceberg via Connect")

    # Sin PURGE: con Nessie el catalogo rechaza borrar los archivos.
    spark.sql(f"DROP TABLE IF EXISTS {TABLA}")
    spark.sql("DROP NAMESPACE IF EXISTS acervo.smoke_connect")
    print("OK  referencia soltada del catalogo")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
