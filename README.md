# acervo

Lakehouse sobre datos publicos: viajes de la TLC de Nueva York y eventos de
GH Archive, descargados de forma incremental, modelados en capas y expuestos
por un API propio.

## Servicios

| Directorio | Que es | Stack |
|---|---|---|
| `ingest/` | Descarga incremental de las fuentes a MinIO | Python |
| `transform/` | Modelado silver y gold | dbt |
| `orchestrate/` | Calendario y dependencias entre trabajos | Dagster |
| `acervo-api/` | API de lectura sobre las tablas gold | Go |
| `acervo-web/` | Dashboard | Next.js + TypeScript |
| `infra/` | Object store, catalogo y motor de proceso | Docker Compose |

## Flujo

```
TLC / GH Archive
      |  ingest      descarga incremental, sin re-bajar lo que ya esta
      v
   MinIO (bronze)    parquet crudo tal como llego
      |  Spark
      v
   Iceberg / Nessie  tablas versionadas, catalogo con ramas
      |  dbt
      v
   silver -> gold    limpio, luego agregado para consumo
      |
      v
   acervo-api -> acervo-web
```

Dagster orquesta todo lo anterior; no es un paso, es el que dispara los pasos.

## Levantar la infraestructura

El repo se gestiona con [devherd](../../personal/devherd), no con `docker
compose` directo. devherd resuelve el compose desde `.devherd.yml`, aplica el
proxy y publica el dominio local.

```bash
cp .env.example .env                  # una sola vez, lo leen Compose y Python
devherd park ~/develop/data-science   # una sola vez
devherd up                            # desde la raiz del repo
devherd proxy apply acervo            # publica acervo.localhost (pide sudo)
```

Comandos utiles:

```bash
devherd plan     # muestra el stack resuelto sin levantar nada
devherd inspect  # busca colisiones con otros proyectos levantados
devherd logs -f  # sigue los logs
devherd down     # baja el proyecto
```

## Verificar que funciona

Tres pruebas, y **prueban cosas distintas**:

```bash
./infra/smoke-test.sh      # el cableado Iceberg <-> Nessie <-> MinIO
./infra/connect-test.sh    # que la config del servidor Spark Connect sirve
./infra/raw-read-test.sh   # que Spark lee el parquet que dejo ingest en raw/
```

`smoke-test.sh` corre `spark-sql` dentro del contenedor, que abre su propia
sesion `local[*]` **con su propia configuracion de catalogo**. Prueba que las
tres piezas se entienden, pero no toca los `--conf` del servidor Connect.

`connect-test.sh` levanta un cliente pyspark externo contra `sc://localhost:15002`
y **no le pasa ninguna configuracion de catalogo**: si `SHOW NAMESPACES IN
acervo` responde, es porque el servidor la tiene bien. Ese es el camino que van
a usar dbt y Dagster.

`raw-read-test.sh` cubre el tramo que los otros dos no tocan: leer una ruta
suelta con `s3a://`. Eso **no pasa por el catalogo**, sino por el FileSystem de
Hadoop, que se configura aparte. Son dos caminos distintos al mismo MinIO y
pueden fallar por separado.

Que los contenedores esten `Up` no demuestra nada: Nessie estuvo `Up` con el
catalogo roto, devolviendo 200 en `/api/v2/config`.

## Por que hay dos archivos compose

`infra/compose.yaml` tiene las definiciones. `compose.yaml` en la raiz solo lo
incluye, y existe porque el detector de devherd solo reconoce un proyecto si
encuentra un compose o un `Dockerfile` **en la raiz**
(`internal/detector/detector.go:205`). Sin el, `devherd up` y `plan` funcionan
—resuelven por `.devherd.yml`— pero `park` no registra el proyecto y entonces
`proxy apply`, `open` y `logs <nombre>` fallan con "project not found".

## Puertos

| Servicio | Puerto | Que es |
|---|---|---|
| MinIO | 9000 | API S3 |
| MinIO | 9001 | Consola web |
| Nessie | 19120 | Catalogo Iceberg + REST |
| Spark | 15002 | Spark Connect |

Credenciales y demas configuracion en `.env.example`, en la raiz. Se copia a
`.env` una vez (`cp .env.example .env`) y de ahi comen tanto Compose como los
servicios de Python. Son valores de desarrollo local: el lakehouse no sale de
la maquina, pero el codigo ya no los trae dentro.

## Estado

Infraestructura levantada y verificada por las dos pruebas. Los cinco servicios
restantes son esqueletos con su README; todavia no hay datos.

Spark habla con Nessie por su catalogo nativo (`NessieCatalog`), no por el
endpoint Iceberg REST. Consecuencia practica: **las credenciales de MinIO las
tiene Spark, no Nessie**, y Nessie no guarda ninguna configuracion de
almacenamiento. El porque esta en el vault, decision 002.

## Documentacion

El *que* vive aqui. El *por que* vive en el vault:
`10 Projects/acervo/`.
