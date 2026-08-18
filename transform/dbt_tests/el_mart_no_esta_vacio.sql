-- Excepcion E1 de CU-003.
--
-- Si el mes no esta en silver, la agregacion no falla: devuelve cero grupos y
-- el mart queda vacio con `dbt run` en verde. **Salir bien sin datos es peor
-- que fallar**, porque nadie lo mira. Esta prueba es lo que distingue "no hay
-- datos" de "el modelo no corrio".
--
-- Un data test de dbt falla cuando devuelve filas, asi que se devuelve una fila
-- justo cuando el mart esta vacio.
select 1 as mart_vacio
where (select count(*) from {{ ref('viajes_por_zona_hora') }}) = 0
