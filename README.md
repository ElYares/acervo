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

```bash
./infra/smoke-test.sh
```

Escribe una tabla Iceberg atravesando Spark, Nessie y MinIO, la lee y la borra.
Es la unica prueba que confirma que las tres piezas estan cableadas entre si;
que los contenedores esten `Up` no demuestra nada.

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

Credenciales por defecto en `infra/.env.example`. Son de desarrollo local: el
lakehouse no sale de la maquina.

## Estado

Infraestructura levantada y verificada con `smoke-test.sh`. Los cinco servicios
restantes son esqueletos con su README; todavia no hay datos.

Spark habla con Nessie por su catalogo nativo (`NessieCatalog`), no por el
endpoint Iceberg REST. Consecuencia practica: **las credenciales de MinIO las
tiene Spark, no Nessie**, y Nessie no guarda ninguna configuracion de
almacenamiento. El porque esta en el vault, decision 002.

## Documentacion

El *que* vive aqui. El *por que* vive en el vault:
`10 Projects/acervo/`.
