# ingest

Descarga incremental de las fuentes publicas a la capa `raw` de MinIO.

## Fuentes

**TLC** — viajes de taxi y VHS de Nueva York. Se publica en parquet, un archivo
por mes y por tipo de servicio (`yellow`, `green`, `fhv`, `fhvhv`).

Comprobado con peticiones `HEAD` reales el 2026-08-04:

```
https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet

mes existente     200, con Content-Length y ETag
mes inexistente   403  <- no 404
yellow 2024-01    47.6 MB
yellow 2009-01    448 MB
```

Dos consecuencias que no son obvias: un backfill que pase del ultimo mes
publicado recibe **403**, no 404, y tratarlo como error de red produce
reintentos infinitos. Y el rango de tamanos es de casi 10x, asi que la descarga
no puede asumir que el archivo cabe en memoria.

**GH Archive** — eventos publicos de GitHub, un archivo `.json.gz` por hora.
Volumen alto y crece sin parar: la ventana a descargar es una decision, no un
"todo".

## Lo que "incremental" tiene que significar aqui

No re-bajar lo que ya esta. Ambas fuentes son archivos inmutables con nombre
predecible, asi que la marca de agua es la existencia del objeto en `raw/`, no
una fecha en una tabla de control.

Casos que hay que resolver y que no son obvios:

- TLC **revisa** meses ya publicados. Un archivo que ya bajaste puede cambiar de
  contenido sin cambiar de nombre. Comparar tamano o etag, no solo existencia
- GH Archive tiene **huecos**: horas que simplemente no existen. Un 404 no es
  necesariamente un error a reintentar
- Bajar un mes de `fhvhv` son varios GB. El streaming a MinIO no puede pasar por
  memoria

## Uso

```bash
uv sync
uv run ingest tlc yellow --mes 2024-01     # descarga a raw/tlc/yellow/2024-01.parquet
uv run ingest tlc yellow --mes 2024-01     # segunda vez: no descarga nada
uv run ingest tlc yellow --mes 2024-01 --forzar
```

Codigos de salida: `0` exito (incluye "ya presente" y "no publicado"), `1` fallo
escribiendo el destino, `2` argumentos invalidos.

Un mes no publicado **no es un fallo**: en un backfill es la senal de que se
llego al final, y salir con error haria reintentar para siempre.

## Como decide si descargar

La marca de agua es el **ETag del origen**, guardado como metadata de usuario
del objeto en MinIO.

| Situacion | Que hace |
|---|---|
| El objeto no existe | Descarga |
| Existe y el ETag coincide | No descarga nada |
| Existe y el ETag difiere | Re-descarga y lo reporta como **revision** |
| El origen responde 403 | Reporta "no publicado" y termina con exito |

No se compara contra el ETag que calcula MinIO: MinIO calcula el suyo sobre lo
que recibio, y en subidas multiparte no coincide con el del origen. El ETag de
`yellow 2024-01` termina en `-3` justamente por eso.

## Como evita objetos parciales

La subida va a `<key>.parcial` y solo se promueve a la clave final si el tamano
subido coincide con el `Content-Length` del origen. Si el proceso muere a la
mitad, lo huerfano es la temporal.

Sin esto, la deteccion de "ya descargado" mentiria: veria el objeto, lo daria
por completo y nunca lo repararia.

## Configuracion

| Variable | Default |
|---|---|
| `ACERVO_S3_ENDPOINT` | `http://localhost:9000` |
| `MINIO_ROOT_USER` | `acervo` |
| `MINIO_ROOT_PASSWORD` | `acervo123` |

## Desarrollo

```bash
uv run pytest                        # todo
uv run pytest -m "not integracion"   # sin MinIO
uv run ruff check .
```

Las pruebas de integracion se saltan solas si MinIO no responde.

## Estado

TLC implementado para un mes y un servicio — CU-001. GH Archive sin empezar.

## Siguiente

Backfill de un rango de meses, apoyado en que un mes ya descargado sale en
0.6 s contra los 4.9 s de una descarga.
