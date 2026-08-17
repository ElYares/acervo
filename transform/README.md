# transform

Materializa las capas modeladas del lakehouse: **silver de TLC con Spark** y
**gold con dbt**, que viven aqui los dos porque son el mismo servicio con dos
herramientas. La frontera esta en la Decision 003 del vault: Spark materializa
silver, dbt entra desde gold.

De gold hoy existe **el puente, no los modelos**: HU-004 dejo probado que dbt
escribe Iceberg contra este stack. El primer mart real es CU-003.

## Capas

**bronze** no vive aqui. Es lo que `ingest` dejo en `raw/`: parquet crudo, sin
tocar. Este servicio lo lee como fuente y no lo modifica.

**silver** — una tabla Iceberg por servicio, tipada y particionada por mes. Una
fila de silver es una fila del origen, tipada y **marcada**. No agrega, no une y
no descarta.

**gold** — agregados listos para consumo, con dbt. Es lo unico que va a leer
`acervo-api`: silver tiene un renglon por viaje y ningun proceso Go va a
escanear millones de filas por peticion HTTP. Todavia sin modelos reales.

## Uso

```bash
uv run silver tlc yellow --mes 2024-01
```

Escribe `acervo.silver.tlc_yellow`, reemplazando la particion del mes. Reporta
filas leidas, marcadas y escritas:

```text
acervo.silver.tlc_yellow  mes=2024-01  leidas=2,964,624  marcadas=124,198 (4.19%)  escritas=2,964,624
```

Codigos de salida: `2` mes o servicio invalido (no abre Spark), `1` el mes no
esta en `raw/`, el esquema no cumple el contrato, o la particion no quedo con
tantas filas que el origen.

Y gold, con dbt:

```bash
uv run dbt debug                        # el puente responde
uv run dbt run --select puente_dbt      # el canario de HU-004
```

`profiles.yml` esta en este directorio y dbt lo encuentra solo: **no hace falta
`DBT_PROFILES_DIR`**.

## Como habla dbt con Spark

Por Spark Connect, sin thrift, sin tocar el `compose.yaml`. Y por un camino que
conviene entender antes de tocarlo.

**`dbt-spark` no soporta Spark Connect.** Su `SparkConnectionMethod` solo declara
`thrift`, `http`, `odbc` y `session`. Funciona igual porque el metodo `session`
arma la sesion asi, en `session.py:116-121`:

```python
builder = SparkSession.builder.enableHiveSupport()
for parameter, value in self.server_side_parameters.items():
    builder = builder.config(parameter, value)
spark_session = builder.getOrCreate()
```

Al pasar `spark.remote` como `server_side_parameter`, el builder de pyspark 3.5
devuelve una sesion **remota**. Es un efecto colateral de como esta escrito el
adaptador, no una capacidad soportada, y de ahi salen tres consecuencias:

- **La version de `dbt-spark` va clavada con `==`.** Una version futura puede
  reordenar ese builder y romperlo sin anunciar nada, porque nunca fue una
  promesa
- **`tests/test_dbt_integracion.py` es lo que hace ruidoso ese riesgo.** Sin esa
  prueba, el dia que se levante el pin dbt levantaria una Spark local en el
  proceso —sin catalogo, sin credenciales— en vez de fallar
- **`enableHiveSupport()` tira un `UserWarning` en cada sentencia**
  (`Cannot modify the value of a static config: spark.sql.catalogImplementation`).
  Es inofensivo: el servidor ya tiene su catalogo estatico

Dos detalles mas del proyecto dbt:

- **`+schema: X` significa literalmente X.** Por defecto dbt concatena y un
  `+schema: puente` sobre el target `gold` daria `gold_puente`. Aqui `silver` y
  `gold` son namespaces reales del catalogo, no prefijos de aislamiento entre
  desarrolladores. Lo corrige `macros/generate_schema_name.sql`
- **`file_format: iceberg` esta puesto a proposito.** El default de dbt-spark
  deja una tabla Hive que Nessie no versiona y que no comparte formato con
  silver

## Por que marca y no filtra

Descartar en silver pierde informacion sin vuelta atras. Una tarifa negativa no
es un error: en `2024-01` son 21,406 disputas y 5,741 viajes sin cargo, todas
operaciones reales que gold no debe sumar como ingreso pero que existieron.

Por eso cada regla es una **columna booleana**, no un `WHERE`. Gold decide.

Las banderas nunca son nulas: van envueltas en `coalesce(..., false)`. Una
bandera nula no esta ni marcada ni limpia, y un `WHERE NOT sin_distancia` en
gold descartaria esas filas en silencio.

## El contrato de columnas

`contrato.py` mapea las 19 columnas del origen a sus nombres y tipos en silver.
Es lo que permite que un mes con el esquema cambiado falle diciendo **que**
columna falto, en vez de "no se pudo leer".

La regla de nombres es la de `ingest`: ingles para lo que nombra la TLC, espanol
para lo que nombra acervo. Por eso `trip_distance` y `pickup_datetime` conviven
con `mes`, `sin_distancia` e `importe_negativo`.

Tres decisiones que no son obvias:

- **Fuera el prefijo `tpep_`**, que es especifico de yellow. `green` usa `lpep_`
  y tiene que caer en el mismo nombre de columna
- **Los importes van a `decimal(10,2)`**, no `double`: sumar millones de double
  en gold acumula error de coma flotante
- **El emparejado ignora mayusculas.** El origen ya mezcla cuatro convenciones
  en el mismo archivo, asi que un cambio de caja entre meses no deberia
  parecerse a una columna que falta

Un servicio nuevo se agrega poniendo su tupla en `CONTRATOS`. No hay que
reestructurar nada: la tabla se llama `tlc_<servicio>` justo por eso.

## Las siete banderas

Estan en `calidad.py` con su condicion y su descripcion. Los umbrales **no son
de memoria**: salen de perfilar `yellow 2024-01` y cada uno tiene su conteo en
la nota de CU-002 del vault. En ese mes las siete juntas marcan el 4.19%.

Dos que suelen sorprender:

- **`velocidad_absurda` en vez de un tope de distancia.** El maximo de
  `trip_distance` del mes son 312,722 millas en un viaje de 13 minutos, pero
  cortar por distancia castigaria un viaje largo legitimo. Un taxi no promedia
  100 mph
- **`pasajeros_cero` mira el cero y no el null.** El null de `passenger_count`
  es una ausencia estructural del origen: cinco columnas que faltan siempre
  juntas en el 4.73% de las filas, cruzando los tres VendorID. No es un defecto

## La escritura

`overwritePartitions()` de Iceberg. Un unico commit: la particion queda completa
o como estaba, nunca a medias, y re-correr el mismo mes lo reemplaza en vez de
duplicarlo.

Esta verificado contra el stack, no deducido del protocolo — el detalle y sus
dos limites estan en E3 de CU-002. El que importa en el dia a dia: **cada
corrida deja un snapshot y el data file anterior sobrevive**, porque lo
referencia la historia. Re-materializar un mes N veces deja N copias en MinIO.
`expire_snapshots` falla con `GC is disabled`, igual que `DROP TABLE PURGE`; es
trabajo del GC de Nessie, que hoy no corre.

## Configuracion

Sale del `.env` unico de la raiz. **Aqui no hay credenciales, y es deliberado**:
este servicio no toca MinIO, se lo pide a Spark, y las claves viven en el
servidor Connect. Si algun dia hicieran falta aqui, seria senal de que se esta
saltando el servidor.

| Variable | Default | Que es |
|---|---|---|
| `ACERVO_SPARK_REMOTE` | `sc://localhost:15002` | Servidor Spark Connect |
| `ACERVO_CATALOGO` | `acervo` | Catalogo Iceberg en Nessie |
| `ACERVO_S3_BUCKET_RAW` | `raw` | Bucket de la capa raw |
| `ACERVO_DBT_SCHEMA` | `gold` | Namespace destino de los modelos dbt |

**Trampa del `.env` con dbt.** El codigo Python de este servicio carga el `.env`
de la raiz con `python-dotenv`, pero `env_var` de dbt lee el entorno **del
proceso** y no sabe nada de ese archivo. Los defaults de `profiles.yml` son los
de desarrollo local, asi que en local no se nota; para apuntar a otro servidor
hay que **exportar** la variable, no escribirla en `.env`.

## Desarrollo

```bash
uv sync
uv run pytest                  # incluye pruebas contra el stack real
uv run pytest -m "not integracion"
uv run ruff check .
```

**Python 3.11, clavado en `.python-version`.** No es un capricho: el cliente de
Connect de pyspark 3.5.6 importa `distutils`, que Python 3.12 elimino de la
stdlib. Con 3.12 instala bien y muere al abrir la sesion. El resto del repo va
en 3.13+; este servicio no puede.

Y `pyspark[connect]` va con `==`, no con `>=`: tiene que ser la version exacta
del servidor. Ver `infra/README.md`.

## Estado

CU-002 implementado para `yellow` y HU-004 cerrada: el puente de dbt esta
probado. Las pruebas de integracion materializan el mes de verdad y tardan
alrededor de un minuto.

`models/puente/puente_dbt.sql` es un canario desechable: no modela nada, existe
para que las pruebas puedan afirmar que el puente aguanta. Se borra cuando
CU-003 traiga un modelo que alguien consulte.

## Siguiente

- CU-003: el primer mart de gold, viajes por zona y hora
- El contrato de `green`, `fhv` y `fhvhv`
- Backfill de varios meses en una corrida

## Deuda conocida

Las tablas nacen con `gc.enabled=false`, asi que dropear una **no** borra sus
archivos de MinIO y cada `dbt run --full-refresh` deja otra copia. Es el mismo
GC de Nessie que no corre y que ya afecta a silver: `expire_snapshots` falla con
`GC is disabled`, igual que `DROP TABLE PURGE`.
