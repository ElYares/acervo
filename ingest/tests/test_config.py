"""La configuracion es codigo: se prueba como codigo.

Lo que se verifica aqui es que faltar una variable sea un fallo temprano y con
nombre propio, no un default silencioso que apunta al almacen equivocado.
"""

import httpx
import pytest
from typer.testing import CliRunner

from acervo_ingest import config, tlc
from acervo_ingest.cli import app

OBLIGATORIAS = ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "ACERVO_TLC_BASE_URL")
OPCIONALES = (
    "ACERVO_S3_ENDPOINT",
    "ACERVO_S3_REGION",
    "ACERVO_S3_BUCKET_RAW",
    "ACERVO_HTTP_TIMEOUT",
)


@pytest.fixture
def entorno_limpio(monkeypatch):
    """Entorno sin ninguna variable del proyecto.

    Se fuerza antes la carga del `.env` —que esta cacheada— para que las
    llamadas siguientes no vuelvan a repoblar lo que aqui se borra.
    """
    config._cargar_env()
    for nombre in OBLIGATORIAS + OPCIONALES:
        monkeypatch.delenv(nombre, raising=False)


@pytest.mark.parametrize(
    ("faltante", "construir"),
    [
        ("MINIO_ROOT_USER", config.S3Config.desde_entorno),
        ("MINIO_ROOT_PASSWORD", config.S3Config.desde_entorno),
        ("ACERVO_TLC_BASE_URL", config.OrigenTLC.desde_entorno),
    ],
)
def test_falta_una_obligatoria_y_el_error_la_nombra(
    entorno_limpio, monkeypatch, faltante, construir
):
    for nombre in OBLIGATORIAS:
        if nombre != faltante:
            monkeypatch.setenv(nombre, "valor")

    with pytest.raises(config.ErrorConfiguracion, match=faltante):
        construir()


def test_una_obligatoria_vacia_cuenta_como_ausente(entorno_limpio, monkeypatch):
    monkeypatch.setenv("MINIO_ROOT_USER", "acervo")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "   ")

    with pytest.raises(config.ErrorConfiguracion, match="MINIO_ROOT_PASSWORD"):
        config.S3Config.desde_entorno()


def test_las_opcionales_traen_default(entorno_limpio, monkeypatch):
    monkeypatch.setenv("MINIO_ROOT_USER", "u")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "p")

    cfg = config.S3Config.desde_entorno()

    assert cfg.endpoint == "http://localhost:9000"
    assert cfg.region == "us-east-1"
    assert cfg.bucket_raw == "raw"


def test_el_entorno_gana_sobre_el_default(entorno_limpio, monkeypatch):
    monkeypatch.setenv("MINIO_ROOT_USER", "u")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "p")
    monkeypatch.setenv("ACERVO_S3_ENDPOINT", "http://minio-remoto:9000")
    monkeypatch.setenv("ACERVO_S3_BUCKET_RAW", "crudo")

    cfg = config.S3Config.desde_entorno()

    assert cfg.endpoint == "http://minio-remoto:9000"
    assert cfg.bucket_raw == "crudo"


def test_la_url_base_pierde_la_diagonal_final(entorno_limpio, monkeypatch):
    monkeypatch.setenv("ACERVO_TLC_BASE_URL", "http://origen/datos/")

    assert config.OrigenTLC.desde_entorno().base_url == "http://origen/datos"


def test_timeout_no_numerico_falla_con_el_nombre(entorno_limpio, monkeypatch):
    monkeypatch.setenv("ACERVO_TLC_BASE_URL", "http://origen/datos")
    monkeypatch.setenv("ACERVO_HTTP_TIMEOUT", "treinta")

    with pytest.raises(config.ErrorConfiguracion, match="ACERVO_HTTP_TIMEOUT"):
        config.OrigenTLC.desde_entorno()


def test_sin_configuracion_la_cli_sale_con_3_y_no_toca_la_red(entorno_limpio, monkeypatch):
    def no_deberia_abrirse(*_args, **_kwargs):
        raise AssertionError("se abrio un cliente HTTP sin configuracion resuelta")

    monkeypatch.setattr(httpx, "Client", no_deberia_abrirse)
    monkeypatch.setattr(tlc.httpx, "Client", no_deberia_abrirse)

    resultado = CliRunner().invoke(app, ["tlc", "yellow", "--mes", "2024-01"])

    assert resultado.exit_code == 3, resultado.output
