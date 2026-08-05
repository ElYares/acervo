# transform

Modelado con dbt sobre las tablas Iceberg del catalogo.

## Capas

**bronze** no vive aqui. Es lo que `ingest` dejo en `raw/`: parquet crudo, sin
tocar. dbt no lo produce, solo lo lee como fuente.

**silver** — una tabla por entidad, limpia y tipada. Aqui se resuelve lo que
esta mal en el origen:

- TLC trae viajes con fechas fuera del mes del archivo, distancias en cero y
  tarifas negativas. Filtrar no es opcional, pero **que** se filtra es una
  decision que hay que dejar escrita
- GH Archive cambio de esquema con los anos. El mismo tipo de evento no trae los
  mismos campos en 2015 y en 2026

**gold** — agregados listos para consumo. Es lo unico que lee `acervo-api`.

## Convenciones

Sin `dbt init` todavia. Cuando se corra, el proyecto va aqui mismo, con
`profiles.yml` apuntando al Spark del compose via Spark Connect.

## Estado

Esqueleto. Nada implementado.

## Siguiente

`dbt init` y un solo modelo silver sobre el mes de TLC que baje `ingest`.
