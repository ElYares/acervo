"""Fuente TLC: viajes de taxi y VHS de Nueva York.

Un archivo parquet por mes y por servicio, inmutable salvo revisiones del
origen. La marca de agua es el ETag, no una fecha: los nombres son predecibles
y el contenido puede cambiar sin que cambie el nombre.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import IO

import httpx

from acervo_ingest.config import OrigenTLC
from acervo_ingest.storage import AlmacenRaw

# Reglas del dominio, no configuracion: cambian cuando cambia TLC, no cuando
# cambia la maquina. La URL del origen si es configuracion y vive en el entorno.
SERVICIOS = ("yellow", "green", "fhv", "fhvhv")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# CloudFront responde 403 —no 404— para un mes que no existe: no distingue
# entre "mes futuro" y "mes inexistente". Tratarlo como error de red hace que
# cualquier backfill que pase del ultimo mes publicado reintente sin fin.
HTTP_NO_PUBLICADO = (403, 404)


class Resultado(StrEnum):
    DESCARGADO = "descargado"
    YA_PRESENTE = "ya_presente"
    REVISION = "revision"
    NO_DISPONIBLE = "no_disponible"


@dataclass(frozen=True)
class Informe:
    resultado: Resultado
    key: str
    bytes: int = 0
    etag: str | None = None


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


class _LectorStream:
    """Adapta un iterador de bytes a algo con `read(n)`, que es lo que espera boto3.

    Existe para que el parquet no pase entero por memoria: con meses de 448 MB
    materializarlo no es opcion.
    """

    def __init__(self, trozos: Iterator[bytes]):
        self._trozos = trozos
        self._buffer = b""

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            resto = self._buffer + b"".join(self._trozos)
            self._buffer = b""
            return resto
        while len(self._buffer) < n:
            try:
                self._buffer += next(self._trozos)
            except StopIteration:
                break
        salida, self._buffer = self._buffer[:n], self._buffer[n:]
        return salida


def ingerir(
    almacen: AlmacenRaw,
    origen: OrigenTLC,
    servicio: str,
    mes: str,
    forzar: bool = False,
) -> Informe:
    url = url_mes(origen.base_url, servicio, mes)
    key = key_destino(servicio, mes)

    with httpx.Client(follow_redirects=True, timeout=origen.timeout) as cliente:
        cabeza = cliente.head(url)

        if cabeza.status_code in HTTP_NO_PUBLICADO:
            return Informe(Resultado.NO_DISPONIBLE, key)
        cabeza.raise_for_status()

        etag = cabeza.headers.get("etag", "").strip('"')
        tamano = int(cabeza.headers["content-length"])

        registrado = almacen.etag_registrado(key)
        if registrado is not None and not forzar:
            if registrado == etag:
                return Informe(Resultado.YA_PRESENTE, key, tamano, etag)
            resultado = Resultado.REVISION
        else:
            resultado = Resultado.DESCARGADO

        with cliente.stream("GET", url) as respuesta:
            respuesta.raise_for_status()
            cuerpo: IO[bytes] = _LectorStream(respuesta.iter_bytes())  # type: ignore[assignment]
            almacen.subir(key, cuerpo, etag, tamano)

    return Informe(resultado, key, tamano, etag)
