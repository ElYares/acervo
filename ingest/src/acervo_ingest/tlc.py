"""Fuente TLC: viajes de taxi y VHS de Nueva York.

Un archivo parquet por mes y por servicio, inmutable salvo revisiones del
origen. La marca de agua es el ETag, no una fecha: los nombres son predecibles
y el contenido puede cambiar sin que cambie el nombre.

El catalogo de zonas es de la misma fuente pero no es un viaje: vive en
`zonas.py`.
"""

import re

from acervo_ingest import descarga
from acervo_ingest.config import OrigenTLC
from acervo_ingest.descarga import Informe
from acervo_ingest.storage import AlmacenRaw

# Reglas del dominio, no configuracion: cambian cuando cambia TLC, no cuando
# cambia la maquina. La URL del origen si es configuracion y vive en el entorno.
SERVICIOS = ("yellow", "green", "fhv", "fhvhv")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# CloudFront responde 403 —no 404— para un mes que no existe: no distingue
# entre "mes futuro" y "mes inexistente". Tratarlo como error de red hace que
# cualquier backfill que pase del ultimo mes publicado reintente sin fin.
#
# Es politica de **los viajes**, no del origen: se pasa a `descargar_si_cambio`
# en cada llamada en vez de vivir en el nucleo, porque el catalogo de zonas se
# baja del mismo host y ahi un 403 si es un fallo.
HTTP_NO_PUBLICADO = (403, 404)


class MesInvalido(ValueError):
    pass


class ServicioInvalido(ValueError):
    pass


def validar(servicio: str, mes: str) -> None:
    if servicio not in SERVICIOS:
        raise ServicioInvalido(f"servicio '{servicio}' no es uno de {', '.join(SERVICIOS)}")
    if not _MES.match(mes):
        raise MesInvalido(f"mes '{mes}' no tiene formato YYYY-MM")


def url_mes(base: str, servicio: str, mes: str) -> str:
    """La URL del parquet de un mes. La base entra por parametro para que esta
    funcion siga siendo pura y probable sin entorno."""
    validar(servicio, mes)
    return f"{base}/{servicio}_tripdata_{mes}.parquet"


def key_destino(servicio: str, mes: str) -> str:
    validar(servicio, mes)
    return f"tlc/{servicio}/{mes}.parquet"


def ingerir(
    almacen: AlmacenRaw,
    origen: OrigenTLC,
    servicio: str,
    mes: str,
    forzar: bool = False,
) -> Informe:
    return descarga.descargar_si_cambio(
        almacen,
        url=url_mes(origen.base_url, servicio, mes),
        key=key_destino(servicio, mes),
        timeout=origen.timeout,
        forzar=forzar,
        ausente_en=HTTP_NO_PUBLICADO,
    )
