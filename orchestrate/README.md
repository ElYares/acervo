# orchestrate

Dagster: que corre, cuando, y en que orden.

## Por que Dagster y no cron

Las dependencias del pipeline son entre **datos**, no entre horarios. Un modelo
gold de viajes por zona depende de que el silver de ese mes exista, no de que
sean las 3am. Dagster modela eso directamente con assets; cron obliga a
adivinar tiempos de espera y a reintentar a ciegas.

## Forma prevista

- Un asset por particion de fuente (mes para TLC, hora o dia para GH Archive)
- Los modelos dbt se cargan como assets, no se disparan con un `dbt run` opaco.
  Asi el grafo llega hasta gold sin cortarse en la frontera de dbt
- Backfill como caso de primera clase: el historico de TLC son mas de diez anos

## Estado

Esqueleto. Nada implementado.

## Siguiente

Dagster levantando y un solo asset: el mes de TLC que baja `ingest`.
Particionado desde el principio — retrofitear particiones despues duele.
