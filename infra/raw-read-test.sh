#!/usr/bin/env bash
# Valida HU-002: un cliente externo lee el parquet que `ingest` dejo en
# s3://raw/ sin recibir ninguna credencial ni endpoint de S3.
#
# Lo que prueba y connect-test.sh no: leer una ruta suelta con s3a:// no pasa
# por el catalogo Iceberg, sino por el FileSystem de Hadoop, que se configura
# aparte. Son dos caminos distintos al mismo MinIO.
#
#   ./infra/raw-read-test.sh [ruta]
set -euo pipefail

CLIENT_IMAGE="python:3.11-slim"
SPARK_VERSION="3.5.6"
PIP_CACHE_VOLUME="acervo-pip-cache"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUTA="${1:-s3a://raw/tlc/yellow/2024-01.parquet}"

PROJECT="${ACERVO_COMPOSE_PROJECT:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT=$(docker ps --filter "name=-spark-1" --format "{{.Names}}" \
            | sed 's/-spark-1$//' | head -1)
fi
if [[ -z "$PROJECT" ]]; then
  echo "no encuentro el contenedor de spark. Levanta el stack con: devherd up" >&2
  exit 1
fi

# El objeto tiene que existir antes de culpar a Spark: sin esto, un fallo de
# lectura y un mes que nunca se ingirio se ven igual.
echo "== el objeto esta en raw/ =="
CLAVE="${RUTA#s3a://}"
if docker run --rm --network "${PROJECT}_default" \
  -e MC_HOST_local="http://${MINIO_ROOT_USER:-acervo}:${MINIO_ROOT_PASSWORD:-acervo123}@minio:9000" \
  minio/mc:RELEASE.2025-04-16T18-13-26Z \
  stat "local/${CLAVE}" >/dev/null 2>&1; then
  echo "OK  s3://${CLAVE}"
else
  echo "FALLO  no existe s3://${CLAVE}. Corre primero: cd ingest && uv run ingest tlc ..." >&2
  exit 1
fi

# --network host para conectarse a sc://localhost:15002, que es como se van a
# conectar dbt y Dagster: desde fuera del compose.
echo "== cliente externo lee raw/ =="
docker run --rm --network host \
  -v "${PIP_CACHE_VOLUME}:/root/.cache/pip" \
  -v "${HERE}/raw-read-test.py:/test.py:ro" \
  "$CLIENT_IMAGE" \
  sh -c "pip install --quiet 'pyspark[connect]==${SPARK_VERSION}' && python /test.py '${RUTA}'"
