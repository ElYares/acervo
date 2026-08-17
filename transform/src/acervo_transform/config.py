"""Configuracion del servicio, leida del entorno.

**Aqui no hay credenciales, y es deliberado.** Este servicio no toca MinIO: le
pide a Spark que lo haga, y las credenciales viven en el servidor Connect. Es
justo lo que demostro HU-002 con `infra/raw-read-test.sh`, que lee `s3a://` sin
recibir ninguna clave. Si algun dia este modulo necesita una, es senal de que se
esta saltando el servidor.

Por eso tampoco hay variables obligatorias: todo tiene un default de desarrollo
razonable y nada muere por falta de secreto, al reves que en `ingest`.
"""

import os
from dataclasses import dataclass
from functools import cache

from dotenv import find_dotenv, load_dotenv


@cache
def _cargar_env() -> None:
    """Carga el `.env` unico de la raiz del repo, si existe.

    Se busca hacia arriba desde este archivo y no desde el directorio de
    trabajo, porque `uv run`, `pytest` y mas adelante Dagster arrancan desde
    sitios distintos. `override=False`: lo ya exportado gana sobre el archivo.
    """
    load_dotenv(find_dotenv(usecwd=False), override=False)


def _opcional(nombre: str, default: str) -> str:
    _cargar_env()
    return os.environ.get(nombre, "").strip() or default


@dataclass(frozen=True)
class SparkConfig:
    """Como se llega al servidor de Spark y que nombres usa el lakehouse."""

    remote: str
    catalogo: str
    bucket_raw: str

    @classmethod
    def desde_entorno(cls) -> "SparkConfig":
        return cls(
            remote=_opcional("ACERVO_SPARK_REMOTE", "sc://localhost:15002"),
            catalogo=_opcional("ACERVO_CATALOGO", "acervo"),
            bucket_raw=_opcional("ACERVO_S3_BUCKET_RAW", "raw"),
        )
