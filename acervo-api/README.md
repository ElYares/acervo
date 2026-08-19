# acervo-api

API de lectura en Go sobre las tablas gold.

## Alcance

Solo lectura. Nada de este servicio escribe al lakehouse: quien escribe es el
pipeline, y mezclar las dos cosas convierte el API en un segundo camino de
escritura sin linaje.

## Uso

```bash
go run ./cmd/acervo-api          # escucha en :8088
curl localhost:8088/salud
curl 'localhost:8088/viajes?mes=2024-01&zona=132&hora=18'
```

Codigos de salida: `3` falta configuracion (se arregla en el `.env`, no
reintentando), `1` el lakehouse no responde al arrancar.

### `GET /viajes`

Filtros, todos opcionales y combinables: `mes`, `zona` (`pu_location_id`),
`hora` (0-23) y `limite`.

```json
{
  "snapshot_id": 166415534416295733,
  "filas": 1,
  "total": 1,
  "viajes": [
    {
      "mes": "2024-01", "zona": 132, "hora": 18,
      "viajes": 7942, "ingreso": "652924.77",
      "distancia_total": 125430.66999999991,
      "duracion_media_seg": 2321.426970536389
    }
  ]
}
```

`filas` es lo que se devuelve y `total` lo que casa el filtro: sin esa
distincion, quien pagina no sabe si hay mas. `snapshot_id` dice de que snapshot
de Iceberg salio la respuesta, para poder afirmar "esto es de antes del ultimo
`dbt run`" en vez de sospecharlo.

Un filtro ilegible es **400**, no una lista vacia con 200: `?hora=25`
devolviendo cero filas seria indistinguible de "no hubo viajes".

### `GET /salud`

Comprueba el camino entero, Nessie y MinIO incluidos, y no solo que el proceso
este vivo. Un `/salud` que siempre devuelve 200 es el problema que este repo ya
tuvo: **`Up` no significa que funcione**.

Si el lakehouse no responde, **503 y no 500**: el servicio esta bien, lo que no
esta es lo de abajo. Eso le dice a quien monitorea que reintente en vez de buscar
un bug aqui.

## Como lee

Sin motor de por medio. `iceberg-go` abre la tabla y lee el parquet desde MinIO
dentro de este proceso.

**La pieza que hace falta explicar es como se encuentra la tabla.** Iceberg
necesita un catalogo que diga cual es el metadata vigente, y aqui el catalogo es
Nessie. Se le pregunta por su **API nativa**:

```
GET /api/v2/trees/main/contents/gold.viajes_por_zona_hora
  -> { "metadataLocation": "s3://warehouse/gold/.../00008-....metadata.json",
       "snapshotId": 166415534416295733 }
```

**Y no por su endpoint Iceberg REST**, que existe y responde
`500 Warehouse 'warehouse' is not known`. Servirlo obligaria a configurarle a
Nessie el warehouse y darle credenciales de S3, que es justo lo que
`infra/compose.yaml` evita a proposito y el cableado que ya fallo tres veces. La
API nativa da la ruta sin tocar el object store, que es todo lo que hace falta.

El reparto queda: **Nessie dice donde, este proceso lee los bytes.**

### Por que aqui si hay credenciales de MinIO

`transform` presume de no tenerlas y este servicio las lleva. No es una
inconsistencia: `transform` se las pide a Spark porque hay un Spark al que
pedirselas. Aqui no hay motor delante y el proceso lee los objetos el mismo, asi
que no puede delegar en nadie.

### El mart vive en memoria

Se puede porque gold es chico **por construccion**: 5,128 filas y 82 KB para un
mes. Leerlo entero tarda 0.02 s. Si algun dia no cupiera, la respuesta no es
paginar aqui sino revisar el grano del mart, que es donde vive esa decision.

El dato solo cambia cuando corre dbt, asi que releer por peticion seria gastar
por nada. Cada `ACERVO_API_REFRESCO_SEG` se le pregunta a Nessie el snapshot
actual —una llamada barata que no toca S3— y **solo si cambio** se relee. Un
`dbt run` se ve sin reiniciar el servicio.

## Configuracion

Sale del `.env` unico de la raiz, buscado hacia arriba desde el directorio de
trabajo. Go no trae nada como `python-dotenv`: que el archivo no exista no es un
error, porque en un contenedor las variables vienen del entorno.

| Variable | Default | Que es |
|---|---|---|
| `MINIO_ROOT_USER` | **sin default** | Credenciales de MinIO |
| `MINIO_ROOT_PASSWORD` | **sin default** | idem |
| `ACERVO_API_ADDR` | `:8088` | El 8080 lo ocupa `dbt docs serve` |
| `ACERVO_API_REFRESCO_SEG` | `30` | Cada cuanto se pregunta por el snapshot |
| `ACERVO_NESSIE_URL` | `http://localhost:19120` | Catalogo |
| `ACERVO_NESSIE_REF` | `main` | Rama de Nessie |
| `ACERVO_GOLD_TABLA` | `gold.viajes_por_zona_hora` | Tabla a servir |

Sin credenciales el proceso **muere nombrando la variable que falta**, con
codigo `3`. Es la Decision 004: arrancar con una clave inventada convierte un
fallo de configuracion en un 403 mucho despues que no dice nada.

## Desarrollo

```bash
go test ./...            # incluye pruebas contra el stack real
go test -short ./...     # solo unitarias, sin stack
go vet ./...
```

Las de integracion se saltan solas si Nessie no responde o si falta el `.env`,
igual que las de `transform`.

## Estado

Sirve `gold.viajes_por_zona_hora` para un mes de yellow.

## Siguiente

- Nombres de zona: hoy `zona` es un id porque el lookup de TLC no se ingiere
- Que `acervo.localhost` apunte aqui y no a la consola de MinIO
- Dockerfile y entrada en `infra/compose.yaml`
