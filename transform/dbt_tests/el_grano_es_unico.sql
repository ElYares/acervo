-- El grano declarado es (mes, pu_location_id, hora). Si se duplicara, `viajes`
-- e `ingreso` se contarian dos veces y el API serviria numeros inflados sin que
-- nada fallara.
select mes, pu_location_id, hora, count(*) as veces
from {{ ref('viajes_por_zona_hora') }}
group by mes, pu_location_id, hora
having count(*) > 1
