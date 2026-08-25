"""Descarga incremental con marca de agua por ETag.

El nucleo que comparten las fuentes: preguntar por el `ETag` antes de bajar
nada, bajar por streaming solo si hace falta, y no dejar objetos parciales.

Lo que **no** vive aqui es que significa cada codigo de estado del origen. Esa
politica entra por `ausente_en` y es distinta por fuente: TLC responde `403`
para un mes no publicado y ese es el final legitimo de un backfill; el catalogo
de zonas no tiene meses, siempre esta publicado, y un `403` suyo es un fallo
real. Meter esa constante aqui haria que una fuente heredara en silencio el
final feliz de la otra.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import IO

import httpx

from acervo_ingest.storage import AlmacenRaw

# `raw/` guarda el archivo del origen byte por byte, y la verificacion
# anti-parcial compara contra `Content-Length`. Las dos cosas exigen que el
# cuerpo llegue **sin comprimir en transporte**.
#
# Con el `Accept-Encoding: gzip, deflate` que httpx manda por defecto,
# CloudFront comprime lo comprimible y entonces: (1) omite `Content-Length`, y
# (2) `iter_bytes()` descomprime de forma transparente, asi que los bytes que
# subiriamos no serian los que el header describe. El parquet de los viajes no
# lo revela porque ya es binario comprimido y CloudFront lo deja pasar; el CSV
# del catalogo si.
CABECERAS = {"Accept-Encoding": "identity"}


class ErrorOrigen(RuntimeError):
    """Fallo leyendo el origen, no escribiendo el destino.

    La distincion importa para quien lee la salida: un fallo de origen se
    reintenta mas tarde, uno de destino se arregla en la maquina.
    """


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


class _LectorStream:
    """Adapta un iterador de bytes a algo con `read(n)`, que es lo que espera boto3.

    Existe para que el cuerpo no pase entero por memoria: con meses de 448 MB
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


def descargar_si_cambio(
    almacen: AlmacenRaw,
    url: str,
    key: str,
    timeout: float,
    forzar: bool = False,
    ausente_en: tuple[int, ...] = (),
) -> Informe:
    """Descarga `url` a `key` solo si el `ETag` del origen cambio.

    `ausente_en` enumera los codigos que significan "el origen no lo publica y
    eso no es un fallo". Vacio por defecto **a proposito**: tratar una respuesta
    de error como final feliz es la excepcion, no la norma, y quien la necesite
    tiene que pedirla por su nombre.
    """
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=CABECERAS) as cliente:
        try:
            cabeza = cliente.head(url)
        except httpx.HTTPError as err:
            raise ErrorOrigen(f"no pude consultar {url}: {err}") from err

        if cabeza.status_code in ausente_en:
            return Informe(Resultado.NO_DISPONIBLE, key)
        if cabeza.is_error:
            raise ErrorOrigen(f"{url} respondio {cabeza.status_code}")

        etag = cabeza.headers.get("etag", "").strip('"')

        # Sin `Content-Length` no hay con que verificar que la descarga llego
        # completa, y sin esa verificacion `subir` publicaria un objeto parcial
        # que la proxima corrida daria por bueno. Preferimos no bajar nada.
        if "content-length" not in cabeza.headers:
            raise ErrorOrigen(
                f"{url} no declaro Content-Length"
                f" (content-encoding: {cabeza.headers.get('content-encoding', 'ninguno')});"
                " sin el no se puede verificar que la descarga sea completa"
            )
        tamano = int(cabeza.headers["content-length"])

        registrado = almacen.etag_registrado(key)
        if registrado is not None and not forzar:
            if registrado == etag:
                return Informe(Resultado.YA_PRESENTE, key, tamano, etag)
            resultado = Resultado.REVISION
        else:
            resultado = Resultado.DESCARGADO

        try:
            with cliente.stream("GET", url) as respuesta:
                if respuesta.is_error:
                    raise ErrorOrigen(f"{url} respondio {respuesta.status_code}")
                cuerpo: IO[bytes] = _LectorStream(respuesta.iter_bytes())  # type: ignore[assignment]
                almacen.subir(key, cuerpo, etag, tamano)
        except httpx.HTTPError as err:
            raise ErrorOrigen(f"no pude descargar {url}: {err}") from err

    return Informe(resultado, key, tamano, etag)
