#!/usr/bin/env bash
# Valida HU-001: un cliente externo se conecta a Spark Connect y consulta el
# catalogo `acervo` sin recibir ninguna configuracion de catalogo.
#
# Es la unica prueba que ejercita los --conf del servidor Connect. smoke-test.sh
# no los toca: abre su propia sesion local[*] con su propia configuracion.
#
#   ./infra/connect-test.sh
set -euo pipefail

CLIENT_IMAGE="python:3.11-slim"
SPARK_VERSION="3.5.6"
PIP_CACHE_VOLUME="acervo-pip-cache"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT="${ACERVO_COMPOSE_PROJECT:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT=$(docker ps --filter "name=-spark-1" --format "{{.Names}}" \
            | sed 's/-spark-1$//' | head -1)
fi
if [[ -z "$PROJECT" ]]; then
  echo "no encuentro el contenedor de spark. Levanta el stack con: devherd up" >&2
  exit 1
fi

# El cliente corre con --network host para conectarse a sc://localhost:15002,
# que es como se va a conectar dbt o Dagster: desde fuera del compose.
echo "== cliente externo =="
docker run --rm --network host \
  -v "${PIP_CACHE_VOLUME}:/root/.cache/pip" \
  -v "${HERE}/connect-test.py:/test.py:ro" \
  "$CLIENT_IMAGE" \
  sh -c "pip install --quiet 'pyspark[connect]==${SPARK_VERSION}' && python /test.py"

# Los objetos tienen que existir aunque el DROP ya solto la referencia:
# con Nessie, borrarlos es trabajo del GC.
echo "== rastro en MinIO =="
OBJETOS=$(docker run --rm --network "${PROJECT}_default" \
  -e MC_HOST_local="http://${MINIO_ROOT_USER:-acervo}:${MINIO_ROOT_PASSWORD:-acervo123}@minio:9000" \
  minio/mc:RELEASE.2025-04-16T18-13-26Z \
  ls -r local/warehouse/smoke_connect 2>/dev/null | wc -l)
if [[ "$OBJETOS" -gt 0 ]]; then
  echo "OK  $OBJETOS objetos escritos en s3://warehouse/smoke_connect"
else
  echo "FALLO  Connect no dejo objetos en MinIO" >&2
  exit 1
fi

echo "== commit en Nessie =="
# Sin pipe directo a grep -q: grep cierra el pipe al primer match y curl muere
# con SIGPIPE, que con `set -o pipefail` se lee como fallo de la peticion.
HISTORIAL=$(curl -sS "http://localhost:19120/api/v2/trees/main/history?maxRecords=5")
if grep -q "smoke_connect" <<<"$HISTORIAL"; then
  echo "OK  Nessie registro el commit de la tabla"
else
  echo "FALLO  Nessie no registro el commit" >&2
  exit 1
fi

echo "== limpieza =="
docker run --rm --network "${PROJECT}_default" \
  -e MC_HOST_local="http://${MINIO_ROOT_USER:-acervo}:${MINIO_ROOT_PASSWORD:-acervo123}@minio:9000" \
  minio/mc:RELEASE.2025-04-16T18-13-26Z \
  rm --recursive --force local/warehouse/smoke_connect >/dev/null 2>&1 || true
echo "OK  buckets limpios"
