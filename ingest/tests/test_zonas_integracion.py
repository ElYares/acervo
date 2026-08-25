"""El catalogo de zonas contra el origen y el MinIO reales.

Requiere el stack levantado (`devherd up`) y salida a internet. Sin eso, se
salta.

Aqui viven los criterios de aceptacion de CU-005 que no se pueden simular: que
el archivo que publica TLC hoy siga siendo el que el codigo espera, y que la
zona 132 resulte un aeropuerto.
"""

import csv
import io

import pytest

from acervo_ingest import zonas
from acervo_ingest.config import ErrorConfiguracion, OrigenZonasTLC
from acervo_ingest.descarga import Resultado
from acervo_ingest.storage import almacen_raw

pytestmark = pytest.mark.integracion

# Verificado con HEAD y GET reales el 2026-08-24. Si TLC revisa el catalogo,
# estos numeros cambian y estas pruebas son el aviso: hay que mirar el diff del
# origen, no aflojar la asercion.
BYTES_ESPERADOS = 12331
ZONAS_ESPERADAS = 265


@pytest.fixture
def almacen():
    try:
        a = almacen_raw()
    except ErrorConfiguracion as err:
        pytest.skip(f"sin configuracion: {err}")
    try:
        a._s3.head_bucket(Bucket="raw")
    except Exception:
        pytest.skip("MinIO no responde; levanta el stack con `devherd up`")
    return a


@pytest.fixture
def origen():
    try:
        return OrigenZonasTLC.desde_entorno()
    except ErrorConfiguracion as err:
        pytest.skip(f"sin configuracion: {err}")


@pytest.fixture
def catalogo(almacen, origen):
    """El catalogo presente en `raw/`. Idempotente: si ya esta, no baja nada."""
    zonas.ingerir(almacen, origen)
    cuerpo = almacen._s3.get_object(Bucket="raw", Key=zonas.KEY_DESTINO)["Body"].read()
    return cuerpo


def _filas(cuerpo: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(cuerpo.decode("utf-8"))))


def test_el_catalogo_llega_completo(catalogo):
    assert len(catalogo) == BYTES_ESPERADOS


def test_se_guarda_como_csv_fiel_al_origen(catalogo):
    # raw/ no transforma. La cabecera del origen trae los nombres entrecomillados
    # y asi tienen que quedar: convertir es trabajo de silver.
    assert catalogo.startswith(b'"LocationID","Borough","Zone","service_zone"')


def test_la_segunda_corrida_no_descarga(almacen, origen, catalogo):
    informe = zonas.ingerir(almacen, origen)

    assert informe.resultado is Resultado.YA_PRESENTE
    assert informe.bytes == BYTES_ESPERADOS


def test_una_marca_falsificada_dispara_revision(almacen, origen, catalogo):
    # A2: es asi como se veria una revision del catalogo por parte de TLC.
    almacen.subir(zonas.KEY_DESTINO, io.BytesIO(catalogo), "etag-viejo", len(catalogo))
    assert almacen.etag_registrado(zonas.KEY_DESTINO) == "etag-viejo"

    informe = zonas.ingerir(almacen, origen)

    assert informe.resultado is Resultado.REVISION
    assert almacen.etag_registrado(zonas.KEY_DESTINO) == informe.etag != "etag-viejo"


def test_la_zona_132_es_un_aeropuerto(catalogo):
    """El criterio que pide la nota de Estado.

    Si esto falla, el emparejado entre `pu_location_id` y el catalogo esta mal y
    todo lo que se construya encima miente.
    """
    fila = next(f for f in _filas(catalogo) if f["LocationID"] == "132")

    assert fila["Zone"] == "JFK Airport"
    assert fila["Borough"] == "Queens"
    assert fila["service_zone"] == "Airports"


def test_hay_265_zonas_con_ids_sin_huecos(catalogo):
    ids = sorted(int(f["LocationID"]) for f in _filas(catalogo))

    assert len(ids) == ZONAS_ESPERADAS
    assert ids == list(range(1, ZONAS_ESPERADAS + 1)), "un hueco deja viajes sin zona"


def test_264_y_265_son_datos_y_no_ausencias(catalogo):
    """Los 9,831 viajes limpios que caen ahi no son sucios.

    El origen distingue "no se de donde salio" de "salio de fuera de NYC". Un
    consumidor que las trate como nulos pierde los dos casos.
    """
    por_id = {f["LocationID"]: f for f in _filas(catalogo)}

    assert por_id["264"]["Borough"] == "Unknown"
    assert por_id["265"]["Zone"] == "Outside of NYC"
