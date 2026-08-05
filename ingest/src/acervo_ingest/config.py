"""Conexion al object store.

Los defaults son los del compose de `infra/`. Se sobreescriben por entorno para
poder apuntar a otro MinIO sin tocar codigo.
"""

import os
from dataclasses import dataclass

BUCKET_RAW = "raw"


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    region: str

    @classmethod
    def desde_entorno(cls) -> "S3Config":
        return cls(
            endpoint=os.environ.get("ACERVO_S3_ENDPOINT", "http://localhost:9000"),
            access_key=os.environ.get("MINIO_ROOT_USER", "acervo"),
            secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "acervo123"),
            region=os.environ.get("ACERVO_S3_REGION", "us-east-1"),
        )
