{#
  CU-003, el primer mart de gold.

  Colapsa los viajes de silver en la pregunta que `acervo-api` va a servir:
  cuantos viajes, cuanto ingreso y cuanto duraron, por zona de recogida y hora
  del dia. Un mes de yellow pasa de 2,964,624 renglones a 5,128.

  **Gold descarta lo que silver marco, y solo eso.** Aqui no hay reglas de
  calidad nuevas: se aplica el criterio que silver ya dejo escrito. Y funciona
  sin `coalesce` porque silver ya blindo cada bandera contra nulos; si algun dia
  dejara de hacerlo, un `not bandera` nula descartaria filas en silencio.

  La lista de banderas viene de `vars`, no escrita a mano: la unica fuente de
  verdad es `acervo_transform.calidad.BANDERAS` y hay una prueba que afirma que
  siguen siendo la misma lista. Sin eso, agregar una octava bandera a silver
  dejaria gold filtrando por siete sin que nadie se entere.
#}
{{
    config(
        materialized='table',
        partition_by='mes',
    )
}}

{%- set banderas = var('banderas_calidad') %}

with limpios as (

    select *
    from {{ source('silver', 'tlc_yellow') }}
    where
        {%- for bandera in banderas %}
        not {{ bandera }}{{ " and" if not loop.last }}
        {%- endfor %}

)

select
    -- El grano incluye `mes`. Sin el, el segundo mes que se materialice se
    -- sumaria encima del primero y el mart mentiria sin avisar.
    mes,
    pu_location_id,

    -- Hora local sin zona: las columnas de silver son `timestamp_ntz`, no son
    -- instantes absolutos. "Las 8" es la hora del reloj de Nueva York.
    hour(pickup_datetime) as hora,

    count(*) as viajes,

    -- `total_amount` es decimal(10,2) por la Decision 006, justo para poder
    -- sumarlo aqui sin acumular error de coma flotante.
    sum(total_amount) as ingreso,

    sum(trip_distance) as distancia_total,
    avg(timestampdiff(SECOND, pickup_datetime, dropoff_datetime)) as duracion_media_seg

from limpios
group by mes, pu_location_id, hour(pickup_datetime)
