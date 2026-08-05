"""Configuracion del servicio, leida del entorno.

Aqui vive **solo lo que cambia entre maquinas**: credenciales, endpoints, el
bucket, la URL del origen y el timeout. Las reglas del dominio TLC —que
servicios publica, que significa un 403, el formato del mes— se quedan en
`tlc.py`. Moverlas al entorno las sacaria del alcance de los tipos y de las
pruebas, que es justo lo contrario de configurar.

Ningun valor de este modulo tiene default si es un secreto: si falta, el
comando muere antes de tocar la red. Un default de conveniencia es como se
termina subiendo a produccion contra el MinIO de desarrollo sin enterarse.
"""

import os
from dataclasses import dataclass
from functools import cache

from dotenv import find_dotenv, load_dotenv


class ErrorConfiguracion(RuntimeError):
    """Falta una variable o su valor no sirve.

    Es distinto de un fallo de origen o de destino: no hay nada que reintentar,
    hay algo que definir.
    """


@cache
def _cargar_env() -> None:
    """Carga el `.env` unico de la raiz del repo, si existe.

    Se busca hacia arriba desde este archivo y no desde el directorio de
    trabajo: `uv run`, `pytest` y mas adelante Dagster arrancan desde sitios
    distintos, y la configuracion no puede depender de eso.

    `override=False` a proposito: lo que ya este exportado en el entorno real
    gana sobre el archivo. El `.env` es el default de desarrollo, no la
    autoridad.
    """
    load_dotenv(find_dotenv(usecwd=False), override=False)


def _obligatoria(nombre: str) -> str:
    _cargar_env()
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ErrorConfiguracion(
            f"falta la variable {nombre}: copia .env.example a .env en la raiz del repo"
        )
    return valor


def _opcional(nombre: str, default: str) -> str:
    _cargar_env()
    return os.environ.get(nombre, "").strip() or default


def _numero(nombre: str, default: float) -> float:
    crudo = _opcional(nombre, "")
    if not crudo:
        return default
    try:
        return float(crudo)
    except ValueError as err:
        raise ErrorConfiguracion(f"{nombre} debe ser un numero, no '{crudo}'") from err


@dataclass(frozen=True)
class S3Config:
    """Como se llega al object store."""

    endpoint: str
    access_key: str
    secret_key: str
    region: str
    bucket_raw: str

    @classmethod
    def desde_entorno(cls) -> "S3Config":
        return cls(
            endpoint=_opcional("ACERVO_S3_ENDPOINT", "http://localhost:9000"),
            access_key=_obligatoria("MINIO_ROOT_USER"),
            secret_key=_obligatoria("MINIO_ROOT_PASSWORD"),
            region=_opcional("ACERVO_S3_REGION", "us-east-1"),
            bucket_raw=_opcional("ACERVO_S3_BUCKET_RAW", "raw"),
        )


@dataclass(frozen=True)
class OrigenTLC:
    """De donde se bajan los parquet de TLC y con cuanta paciencia.

    `base_url` es obligatoria aunque no sea un secreto: ninguna URL del origen
    vive en `src/`, y el valor de desarrollo esta en `.env.example`.
    """

    base_url: str
    timeout: float

    @classmethod
    def desde_entorno(cls) -> "OrigenTLC":
        return cls(
            base_url=_obligatoria("ACERVO_TLC_BASE_URL").rstrip("/"),
            timeout=_numero("ACERVO_HTTP_TIMEOUT", 30.0),
        )
