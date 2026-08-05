#!/usr/bin/env bash
# Prueba de humo del lakehouse: escribe una tabla Iceberg atravesando
# Spark -> Nessie -> MinIO, la lee de vuelta y la borra.
#
# Si esto pasa, las tres piezas estan bien cableadas entre si. Si falla, el
# error dice cual de las tres.
#
#   ./infra/smoke-test.sh
set -euo pipefail

PROJECT="${ACERVO_COMPOSE_PROJECT:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT=$(docker ps --filter "name=-spark-1" --format "{{.Names}}" \
            | sed 's/-spark-1$//' | head -1)
fi
if [[ -z "$PROJECT" ]]; then
  echo "no encuentro el contenedor de spark. Levanta el stack con: devherd up" >&2
  exit 1
fi

CATALOG_CONF=(
  --packages org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.9.1,org.apache.iceberg:iceberg-aws-bundle:1.9.1,org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.104.3
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,org.projectnessie.spark.extensions.NessieSparkSessionExtensions
  --conf spark.sql.catalog.acervo=org.apache.iceberg.spark.SparkCatalog
  --conf spark.sql.catalog.acervo.catalog-impl=org.apache.iceberg.nessie.NessieCatalog
  --conf spark.sql.catalog.acervo.uri=http://nessie:19120/api/v2
  --conf spark.sql.catalog.acervo.ref=main
  --conf spark.sql.catalog.acervo.warehouse=s3://warehouse/
  --conf spark.sql.catalog.acervo.io-impl=org.apache.iceberg.aws.s3.S3FileIO
  --conf spark.sql.catalog.acervo.s3.endpoint=http://minio:9000
  --conf spark.sql.catalog.acervo.s3.path-style-access=true
)

echo "usando proyecto compose: $PROJECT"

docker exec "${PROJECT}-spark-1" /opt/spark/bin/spark-sql "${CATALOG_CONF[@]}" -e "
  CREATE NAMESPACE IF NOT EXISTS acervo.smoke;
  CREATE TABLE IF NOT EXISTS acervo.smoke.t (id BIGINT, nota STRING) USING iceberg;
  INSERT INTO acervo.smoke.t VALUES (1, 'lakehouse vivo');
  SELECT * FROM acervo.smoke.t;
" 2>/dev/null | grep -E "lakehouse vivo" && echo "OK  escritura y lectura Iceberg" || {
  echo "FALLO  la tabla no se pudo escribir o leer" >&2
  exit 1
}

# Sin PURGE: con Nessie el catalogo rechaza borrar los archivos, porque otras
# ramas pueden estar referenciandolos. Aqui solo se suelta la referencia.
docker exec "${PROJECT}-spark-1" /opt/spark/bin/spark-sql "${CATALOG_CONF[@]}" -e "
  DROP TABLE IF EXISTS acervo.smoke.t;
  DROP NAMESPACE IF EXISTS acervo.smoke;
" >/dev/null 2>&1 && echo "OK  referencia soltada del catalogo" \
  || echo "AVISO  el DROP fallo, revisa acervo.smoke a mano" >&2

# El DROP deja los objetos en MinIO: borrarlos es trabajo del GC de Nessie, que
# aqui no corre. Sin este paso cada corrida acumula parquet huerfanos en
# warehouse/, que nadie referencia y nadie limpia.
docker run --rm --network "${PROJECT}_default" \
  -e MC_HOST_local="http://${MINIO_ROOT_USER:-acervo}:${MINIO_ROOT_PASSWORD:-acervo123}@minio:9000" \
  minio/mc:RELEASE.2025-04-16T18-13-26Z \
  rm --recursive --force local/warehouse/smoke >/dev/null 2>&1

echo "OK  objetos huerfanos eliminados"
