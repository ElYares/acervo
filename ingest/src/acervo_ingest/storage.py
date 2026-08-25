"""Escritura en la capa raw.

Dos responsabilidades que el resto del codigo no debe reimplementar: leer la
marca de agua de un objeto y subir sin dejar objetos parciales.
"""

from contextlib import suppress
from typing import IO

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from acervo_ingest.config import S3Config

# Clave de la metadata donde vive la marca de agua. No se compara nunca contra
# el ETag que calcula MinIO: MinIO calcula el suyo sobre lo que recibio, y en
# subidas multiparte no coincide con el del origen.
META_ETAG_ORIGEN = "source-etag"


class ErrorAlmacenamiento(RuntimeError):
    """Fallo escribiendo o leyendo el destino, no el origen."""


class AlmacenRaw:
    def __init__(self, cfg: S3Config):
        self._bucket = cfg.bucket_raw
        self._s3 = boto3.client(
            "s3",
            endpoint_url=cfg.endpoint,
            aws_access_key_id=cfg.access_key,
            aws_secret_access_key=cfg.secret_key,
            region_name=cfg.region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def etag_registrado(self, key: str) -> str | None:
        """La marca de agua del objeto, o None si el objeto no existe."""
        try:
            resp = self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as err:
            codigo = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if codigo == 404:
                return None
            raise ErrorAlmacenamiento(f"no pude consultar {key}: {err}") from err
        except BotoCoreError as err:
            # `ClientError` es solo lo que S3 contesta. Que MinIO no conteste
            # —endpoint caido, DNS, timeout— es `BotoCoreError`, y sin este
            # brazo se escapa como traceback en vez del mensaje que distingue
            # el destino del origen.
            raise ErrorAlmacenamiento(f"no pude consultar {key}: {err}") from err
        return resp.get("Metadata", {}).get(META_ETAG_ORIGEN)

    def subir(self, key: str, cuerpo: IO[bytes], etag_origen: str, tamano_esperado: int) -> None:
        """Sube por streaming y solo publica la clave final si el tamano cuadra.

        La subida va a una clave temporal. Si el proceso muere a la mitad, lo que
        queda huerfano es la temporal, no `key` — asi la siguiente corrida no
        confunde un objeto parcial con uno completo y lo repara.
        """
        key_temp = f"{key}.parcial"
        try:
            self._s3.upload_fileobj(
                cuerpo,
                self._bucket,
                key_temp,
                ExtraArgs={"Metadata": {META_ETAG_ORIGEN: etag_origen}},
            )
        except (ClientError, BotoCoreError) as err:
            self._borrar_silencioso(key_temp)
            raise ErrorAlmacenamiento(f"no pude escribir {key_temp}: {err}") from err

        try:
            subido = self._s3.head_object(Bucket=self._bucket, Key=key_temp)["ContentLength"]
            if subido != tamano_esperado:
                raise ErrorAlmacenamiento(
                    f"descarga incompleta de {key}: "
                    f"se esperaban {tamano_esperado} bytes y llegaron {subido}"
                )
            self._s3.copy_object(
                Bucket=self._bucket,
                Key=key,
                CopySource={"Bucket": self._bucket, "Key": key_temp},
                MetadataDirective="COPY",
            )
        finally:
            self._borrar_silencioso(key_temp)

    def _borrar_silencioso(self, key: str) -> None:
        with suppress(ClientError, BotoCoreError):
            self._s3.delete_object(Bucket=self._bucket, Key=key)


def almacen_raw() -> AlmacenRaw:
    """El almacen configurado desde el entorno.

    Lanza `ErrorConfiguracion` si falta una credencial, antes de abrir ninguna
    conexion.
    """
    return AlmacenRaw(S3Config.desde_entorno())
