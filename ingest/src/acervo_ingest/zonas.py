"""Fuente TLC: el catalogo de zonas.

265 zonas en un CSV de 12 KB. Es lo que convierte `pu_location_id` de un numero
en un lugar, y por eso lo necesita cualquier consumidor que quiera dibujar algo.

Tres cosas lo separan de los viajes:

- **No es mensual.** No hay `--mes` ni rango que recorrer; es un archivo unico
  versionado solo por su `ETag`
- **No es parquet.** `raw/` guarda el CSV tal como llego; convertirlo es trabajo
  de silver
- **No tiene un 403 legitimo.** El catalogo siempre esta publicado, asi que
  cualquier respuesta que no sea `200` es un fallo real y no el final de un
  backfill. De ahi que no se le pase `ausente_en`
"""

from acervo_ingest import descarga
from acervo_ingest.config import OrigenZonasTLC
from acervo_ingest.descarga import Informe
from acervo_ingest.storage import AlmacenRaw

# No cuelga de `raw/tlc/<servicio>/`: el catalogo no pertenece a ningun
# servicio, los describe a los cuatro.
KEY_DESTINO = "tlc/zonas.csv"


def ingerir(
    almacen: AlmacenRaw,
    origen: OrigenZonasTLC,
    forzar: bool = False,
) -> Informe:
    return descarga.descargar_si_cambio(
        almacen,
        url=origen.url,
        key=KEY_DESTINO,
        timeout=origen.timeout,
        forzar=forzar,
    )
