# acervo-api

API de lectura en Go sobre las tablas gold.

## Alcance

Solo lectura. Nada de este servicio escribe al lakehouse: quien escribe es el
pipeline, y mezclar las dos cosas convierte el API en un segundo camino de
escritura sin linaje.

## Como lee

Pendiente de decidir, y es la decision que define el servicio:

- **Iceberg directo desde Go** — `iceberg-go` esta joven pero evita depender de
  un motor levantado
- **DuckDB embebido** leyendo el parquet de gold — rapido y simple, pero duplica
  la logica de que es "gold"
- **Trino o Spark por JDBC** — completo, pero mete una dependencia pesada en el
  camino de cada request

No se decide en abstracto: se decide cuando exista la primera tabla gold real y
se pueda medir.

## Estado

Esqueleto. Sin `go mod init` todavia — el modulo se crea cuando haya algo que
compilar.

## Convenciones del repo

El sufijo `-server` que uso en otros repos aqui es `-api`, porque `acervo-web`
tambien es un servidor. El sufijo nombra el rol, no la tecnologia.
