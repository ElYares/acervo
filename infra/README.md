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

Consola de MinIO: http://localhost:9001 (usuario y clave en el `.env.example`
de la raiz del repo).

## Dos caminos a MinIO, y se configuran aparte

Spark llega al mismo MinIO por dos rutas que no comparten nada:

| Cuando | Quien resuelve | Se configura con |
|---|---|---|
| `spark.sql("SELECT * FROM acervo.x.y")` | `S3FileIO` de Iceberg | `spark.sql.catalog.acervo.s3.*` |
| `spark.read.parquet("s3a://raw/...")` | `S3AFileSystem` de Hadoop | `spark.hadoop.fs.s3a.*` |

Tener el catalogo funcionando **no implica** poder leer una ruta suelta. La
primera vez que se intento, con el catalogo perfecto, la lectura murio con
`ClassNotFoundException: org.apache.hadoop.fs.s3a.S3AFileSystem`: ni siquiera
era configuracion, era que faltaba el jar.

Dos consecuencias al tocar el compose:

- **`hadoop-aws` tiene que coincidir con el Hadoop de la imagen**, que es
  3.3.4 (`ls /opt/spark/jars | grep hadoop-client`). Arrastra
  `aws-java-sdk-bundle` v1, que no es el SDK v2 que trae `iceberg-aws-bundle`.
  Cada camino usa el suyo y ambos jars conviven
- El proveedor de credenciales de S3A se declara explicito
  (`SimpleAWSCredentialsProvider`). Con la cadena por defecto, S3A prueba
  proveedores en orden y acaba intentando credenciales de instancia IAM que
  aqui no existen, lo que convierte un fallo de configuracion en un timeout
  que no dice nada

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
