# infra

Object store, catalogo y motor de proceso. Todo local, todo efimero salvo los
volumenes.

## Piezas

**MinIO** — object store compatible con S3. Es el disco del lakehouse. Dos
buckets, creados por el job `minio-init` al levantar:

- `raw/` — lo que baja `ingest`, tal como llego
- `warehouse/` — las tablas Iceberg

**Nessie** — catalogo Iceberg con ramas tipo git. Esto es lo que permite
transformar sobre una rama, validar, y hacer merge a `main` solo si el
resultado cuadra. Persiste en RocksDB sobre un volumen.

**Spark** — motor de proceso, en modo Spark Connect. Lee y escribe Iceberg
contra Nessie usando MinIO como almacenamiento.

## Levantar

Desde la raiz del repo, no desde aqui:

```bash
devherd up
```

devherd lee `.devherd.yml` de la raiz, que apunta a `infra/compose.yaml`.
Llamar a `docker compose` directo funciona, pero se salta el preflight, el
override del proxy y el registro del proyecto.

## Verificar

```bash
docker compose -f infra/compose.yaml ps
curl -fsS http://localhost:19120/api/v2/config    # Nessie responde
```

Consola de MinIO: http://localhost:9001 (usuario y clave en `.env.example`).

## Por que no hay Dockerfiles

Los cuatro servicios corren de imagenes upstream sin modificar. En cuanto haga
falta empaquetar codigo propio (el API de Go, los jobs de Spark), eso vive en
el directorio del servicio, no aqui.

## Notas

- Las credenciales son de desarrollo local y estan en claro a proposito. Nada
  de esto se expone fuera de la maquina
- Los volumenes (`minio-data`, `nessie-data`, `spark-ivy`) sobreviven a
  `devherd down`. Para empezar de cero:
  `docker compose -f infra/compose.yaml down -v`
- `spark-ivy` cachea los jars de Iceberg y AWS entre reinicios; sin el, cada
  arranque los vuelve a bajar
