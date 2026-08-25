"""El catalogo de zonas, sin red.

Aqui solo se prueba lo que distingue al catalogo de los viajes. La mecanica de
descarga es de `descarga.py` y se prueba en `test_descarga.py`.
"""

import inspect

from acervo_ingest import descarga, tlc, zonas
from acervo_ingest.config import OrigenZonasTLC


def test_la_clave_no_cuelga_de_ningun_servicio():
    assert zonas.KEY_DESTINO == "tlc/zonas.csv"
    for servicio in tlc.SERVICIOS:
        assert not zonas.KEY_DESTINO.startswith(f"tlc/{servicio}/"), (
            "el catalogo describe a los cuatro servicios; no pertenece a ninguno"
        )


def test_zonas_no_es_un_servicio_de_viaje():
    # Meterlo en SERVICIOS convertiria esa tupla en "cosas de TLC" y dejaria de
    # validar nada: `ingest tlc zonas --mes 2024-01` pasaria el validador.
    assert "zonas" not in tlc.SERVICIOS


def test_la_url_se_usa_tal_cual_sin_construirla(monkeypatch):
    # El catalogo no tiene patron de nombre que armar: la variable ya trae la
    # URL completa. Si alguien empieza a concatenarle sufijos, esto lo delata.
    vista = {}

    def espia(almacen, url, key, timeout, forzar=False, ausente_en=()):
        vista.update(url=url, key=key, ausente_en=ausente_en, forzar=forzar)

    monkeypatch.setattr(descarga, "descargar_si_cambio", espia)
    origen = OrigenZonasTLC(url="https://origen.invalido/misc/taxi_zone_lookup.csv", timeout=7.0)

    zonas.ingerir(object(), origen)

    assert vista["url"] == origen.url
    assert vista["key"] == zonas.KEY_DESTINO


def test_para_el_catalogo_ningun_codigo_es_final_feliz(monkeypatch):
    """La regla que separa este caso de CU-001.

    En los viajes un 403 significa "mes no publicado" y cierra un backfill. El
    catalogo no tiene meses: siempre esta publicado, asi que un 403 es un fallo
    real. Heredar `HTTP_NO_PUBLICADO` dejaria `raw/` sin catalogo en silencio.
    """
    vista = {}

    def espia(almacen, url, key, timeout, forzar=False, ausente_en=()):
        vista["ausente_en"] = ausente_en

    monkeypatch.setattr(descarga, "descargar_si_cambio", espia)

    zonas.ingerir(object(), OrigenZonasTLC(url="https://origen.invalido/x.csv", timeout=1.0))

    assert vista["ausente_en"] == ()
    assert vista["ausente_en"] != tlc.HTTP_NO_PUBLICADO


def test_ingerir_no_pide_mes():
    # El contrato del catalogo no tiene dimension temporal.
    assert "mes" not in inspect.signature(zonas.ingerir).parameters
