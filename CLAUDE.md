# acervo

<!-- Este archivo se carga en CADA sesion de Claude Code.
     Cada linea cuesta tokens para siempre. Mantenlo bajo ~80 lineas.
     Arquitectura y detalle van en el vault, no aqui. -->

## Que es

Lakehouse sobre datos publicos: viajes de la TLC de Nueva York y eventos de
GH Archive, ingeridos de forma incremental, modelados en capas y expuestos por
un API propio. Proyecto personal, un solo desarrollador.

## Stack

- MinIO (S3) + Nessie (catalogo Iceberg con ramas) + Spark 3.5.6 Connect
- Python 3.13 con **uv** por servicio; dbt y Dagster pendientes
- Go 1.26 para el API, Next.js para el dashboard: **todavia vacios**
- Docker Compose gestionado por **devherd**

## Layout

```text
infra/        compose, pruebas del stack        <- implementado
ingest/       descarga incremental a raw/       <- implementado (TLC)
transform/    silver con Spark, gold con dbt    <- implementado (TLC yellow)
orchestrate/  Dagster                           <- vacio
acervo-api/   Go, lectura sobre gold            <- vacio
acervo-web/   Next.js                           <- vacio
```

Cada servicio Python tiene su propio `pyproject.toml` y su `.venv`. No hay
entorno unico en la raiz.

## Comandos

```bash
cp .env.example .env          # una sola vez; el mismo .env lo leen Compose y Python
devherd up                    # levanta el stack (NUNCA docker compose directo)
devherd down
./infra/smoke-test.sh         # cableado Iceberg <-> Nessie <-> MinIO
./infra/connect-test.sh       # que la config del servidor Spark Connect sirve
./infra/raw-read-test.sh      # que Spark lee con s3a:// el parquet de raw/

cd ingest && uv run pytest              # incluye pruebas contra MinIO real
cd ingest && uv run ruff check .
cd ingest && uv run ingest tlc yellow --mes 2024-01

cd transform && uv run pytest           # incluye pruebas contra Spark y Nessie
cd transform && uv run ruff check .
cd transform && uv run silver tlc yellow --mes 2024-01
cd transform && uv run dbt run          # materializa gold
cd transform && uv run dbt test
```

No hay CI ni task runner en la raiz. Correr las pruebas es manual y por
servicio.

## Convenciones

- **Todo Docker pasa por devherd.** Resuelve el compose desde `.devherd.yml`,
  aplica el proxy y registra el proyecto. `docker compose` directo se salta todo
- **El `compose.yaml` de la raiz no es redundante**: solo incluye a
  `infra/compose.yaml`, y existe porque el detector de devherd exige un compose
  en la raiz o no registra el proyecto
- **`Up` no significa que funcione.** Nessie estuvo `Up` con el catalogo roto
  devolviendo 200. Verificar con los scripts, no con `ps`
- **Verificar antes de afirmar.** Los datos del origen TLC (403 y no 404,
  tamanos de 47 MB a 448 MB) salieron de peticiones reales, no de memoria
- Ramas `feat/*` con PR a `main`. Commits en Conventional Commits, en espanol
- Las notas del vault se escriben **sin acentos**, siguiendo el resto del vault

## Donde buscar

- El **por que** de cualquier decision: vault, `10 Projects/acervo/`
  - `acervo - Estado.md` — foto de hoy, se lee al arrancar (`/contexto`)
  - `Decisions/` — decisiones con su criterio
  - `Backlog/` — HU y CU con criterios de aceptacion verificables
  - `Bitacora/` — que paso y por que, append-only
- Trampas del stack local: `infra/README.md`
- Semantica de la ingesta incremental: `ingest/README.md`
