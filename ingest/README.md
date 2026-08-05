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

## Estado

Esqueleto. Nada implementado.

## Siguiente

Un solo mes de TLC `yellow`, aterrizado en `raw/`, con la deteccion de "ya esta
descargado" funcionando. Es el caso mas simple de la fuente mas estable.
