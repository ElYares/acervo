{#
  El canario de HU-004. No modela nada: existe para que una prueba pueda afirmar
  que dbt llega al servidor de Spark Connect, escribe Iceberg de verdad y el
  commit queda en Nessie.

  Lee silver a proposito, en vez de un `select 1`. Escribir sin leer probaria la
  mitad del puente, y lo que gold va a hacer siempre es leer silver.

  Es desechable. Cuando CU-003 traiga el primer mart real, este modelo se borra:
  su trabajo lo hara un modelo que alguien consulta.
#}
select
    count(*) as filas_en_silver
from {{ env_var('ACERVO_CATALOGO', 'acervo') }}.silver.tlc_yellow
