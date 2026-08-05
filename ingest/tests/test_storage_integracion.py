"""Pruebas contra el MinIO real del compose.

Requieren el stack levantado (`devherd up`). Sin el, se saltan.

Lo que se prueba aqui no se puede probar con mocks sin volver a implementar el
comportamiento de S3: que una subida truncada no deje una clave final que la
siguiente corrida confunda con completa.
"""

import io
import uuid

import pytest

from acervo_ingest.storage import ErrorAlmacenamiento, almacen_raw

pytestmark = pytest.mark.integracion


@pytest.fixture
def almacen():
    a = almacen_raw()
    try:
        a._s3.head_bucket(Bucket="raw")
    except Exception:
        pytest.skip("MinIO no responde; levanta el stack con `devherd up`")
    return a


@pytest.fixture
def key(almacen):
    k = f"_pruebas/{uuid.uuid4()}.bin"
    yield k
    almacen._borrar_silencioso(k)
    almacen._borrar_silencioso(f"{k}.parcial")


def test_subida_completa_registra_la_marca_de_agua(almacen, key):
    datos = b"x" * 1024
    almacen.subir(key, io.BytesIO(datos), "etag-de-prueba", len(datos))

    assert almacen.etag_registrado(key) == "etag-de-prueba"


def test_subida_truncada_no_publica_la_clave_final(almacen, key):
    # E2: el cuerpo entrega menos bytes de los que declaro el origen, que es lo
    # que pasa cuando la transferencia se corta a la mitad.
    datos = b"x" * 500
    with pytest.raises(ErrorAlmacenamiento, match="incompleta"):
        almacen.subir(key, io.BytesIO(datos), "etag-de-prueba", 1024)

    assert almacen.etag_registrado(key) is None, (
        "la clave final no debe existir: si existe, la proxima corrida la da por "
        "completa y nunca la repara"
    )


def test_subida_truncada_no_deja_parcial_huerfano(almacen, key):
    with pytest.raises(ErrorAlmacenamiento):
        almacen.subir(key, io.BytesIO(b"x" * 10), "etag-de-prueba", 999)

    assert almacen.etag_registrado(f"{key}.parcial") is None


def test_objeto_inexistente_no_tiene_marca_de_agua(almacen):
    assert almacen.etag_registrado(f"_pruebas/{uuid.uuid4()}.noexiste") is None
