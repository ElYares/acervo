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
escribiendo el destino, `2` argumentos invalidos, `3` configuracion incompleta.

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

Todo sale del `.env` unico de la raiz del repo. Se copia una vez:

```bash
cp .env.example .env
```

| Variable | Obligatoria | Default |
|---|---|---|
| `MINIO_ROOT_USER` | si | — |
| `MINIO_ROOT_PASSWORD` | si | — |
| `ACERVO_TLC_BASE_URL` | si | — |
| `ACERVO_S3_ENDPOINT` | no | `http://localhost:9000` |
| `ACERVO_S3_REGION` | no | `us-east-1` |
| `ACERVO_S3_BUCKET_RAW` | no | `raw` |
| `ACERVO_HTTP_TIMEOUT` | no | `30` |

Las obligatorias **no tienen default a proposito**. Si falta una, el comando
sale con codigo `3` nombrandola, sin haber hecho ninguna peticion. Un default
de conveniencia es como se termina corriendo contra el almacen equivocado sin
enterarse.

`ACERVO_TLC_BASE_URL` no es un secreto y aun asi es obligatoria: ninguna URL
del origen vive en `src/`, y el valor de desarrollo esta en `.env.example`.

Lo que **no** es configuracion y por eso sigue en el codigo: que servicios
publica TLC, el formato del mes, que un 403 significa "no publicado" y la clave
de metadata donde va la marca de agua. Son reglas del dominio; en un `.env`
quedarian sin tipos y sin pruebas.

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
