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

**TLC, catalogo de zonas** — las 265 zonas a las que apunta `pu_location_id`.
Es lo que convierte ese id en un lugar.

Comprobado con `HEAD` y `GET` reales el 2026-08-24:

```
https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv

200, text/csv, 12,331 bytes, 265 zonas mas cabecera
columnas: LocationID, Borough, Zone, service_zone
132 -> Queens / JFK Airport / Airports
264 -> Unknown / N/A        265 -> N/A / Outside of NYC
```

Tres diferencias con los viajes, y cada una rompe un supuesto del codigo que ya
estaba:

- **Vive en `/misc/`, no bajo `/trip-data/`.** Es una URL hermana, no un sufijo,
  asi que tiene su propia variable de entorno en vez de derivarse de la otra
- **No es mensual.** No hay `--mes`; es un archivo unico versionado solo por su
  `ETag`
- **Un 403 aqui SI es un fallo.** No existe un "catalogo futuro": si el origen
  no responde 200, algo se rompio. Heredar el "no publicado" de los viajes
  dejaria `raw/` sin catalogo en silencio

Las zonas 264 y 265 merecen atencion aparte: **no son datos faltantes**. El
origen distingue "no se de donde salio" de "salio de fuera de NYC", y los 9,831
viajes limpios de `2024-01` que caen ahi son reales. Tratarlas como nulos los
pierde.

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

uv run ingest tlc-zonas                    # descarga a raw/tlc/zonas.csv
uv run ingest tlc-zonas --forzar
```

`tlc-zonas` es comando **hermano** de `tlc` y no `tlc zonas`: ese grupo lleva el
servicio como argumento posicional y el catalogo no es un servicio. Colgarlo ahi
obligaria a meter un centinela en `SERVICIOS` y `ingest tlc zonas --mes 2024-01`
pasaria el validador.

La clave es `raw/tlc/zonas.csv`, fuera de `raw/tlc/<servicio>/`: el catalogo no
pertenece a ningun servicio, los describe a los cuatro. Y se guarda **CSV**,
como llego: convertir a parquet es trabajo de silver.

Codigos de salida: `0` exito (incluye "ya presente" y "no publicado"), `1` fallo
leyendo el origen **o** escribiendo el destino —el mensaje dice cual—, `2`
argumentos invalidos, `3` configuracion incompleta.

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
| El origen responde 403 y la fuente lo permite | Reporta "no publicado" y termina con exito |
| El origen responde 403 y la fuente **no** lo permite | Falla con codigo `1` |

Ese "y la fuente lo permite" es el parametro `ausente_en` de
`descarga.descargar_si_cambio`, y esta **vacio por defecto**. Perdonar una
respuesta de error es la excepcion, no la norma: los viajes la piden por su
nombre (`HTTP_NO_PUBLICADO`), el catalogo no.

No se compara contra el ETag que calcula MinIO: MinIO calcula el suyo sobre lo
que recibio, y en subidas multiparte no coincide con el del origen. El ETag de
`yellow 2024-01` termina en `-3` justamente por eso.

## El cuerpo se pide sin comprimir, y no es un detalle

Todas las peticiones mandan `Accept-Encoding: identity`. Sin eso, con el
`gzip, deflate` que httpx manda por defecto:

```
CSV del catalogo, Accept-Encoding: gzip     ->  content-encoding: gzip
                                                content-length: AUSENTE
CSV del catalogo, Accept-Encoding: identity ->  content-length: 12331
parquet de viajes, cualquiera de los dos    ->  content-length: 49961641
```

CloudFront comprime lo comprimible, y cuando lo hace **omite
`Content-Length`**. Encima httpx descomprime `iter_bytes()` de forma
transparente, asi que los bytes que subiriamos no serian los que el header
describe. Eso rompe las dos garantias de esta capa a la vez: `raw/` deja de ser
fiel al origen, y la verificacion anti-parcial compara el tamano comprimido
contra el descomprimido.

**El parquet de los viajes nunca lo revelo** porque ya es binario comprimido y
CloudFront lo deja pasar intacto. Aparecio al primer CSV.

Y si aun asi falta `Content-Length`, no se descarga nada: sin tamano declarado
no hay con que verificar que la descarga llego completa, y un objeto parcial en
`raw/` se da por bueno para siempre.

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
| `ACERVO_TLC_ZONAS_URL` | si | — |
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

`ACERVO_TLC_ZONAS_URL` es una variable aparte y **no se deriva** de la anterior.
El catalogo vive en `/misc/`, hermana de `/trip-data/`: recortar una para armar
la otra seria construir una URL de origen dentro de `src/`. Separadas tambien
por acoplamiento — que falte la del catalogo no rompe la ingesta de viajes.

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

TLC implementado para un mes y un servicio — CU-001. Catalogo de zonas
implementado — CU-005. GH Archive sin empezar.

## Siguiente

Backfill de un rango de meses, apoyado en que un mes ya descargado sale en
0.6 s contra los 4.9 s de una descarga.

El catalogo de zonas ya esta en `raw/`, pero **nadie lo consume todavia**:
silver no tiene tabla de zonas y gold sigue devolviendo el id. Eso es otro caso
de uso.
