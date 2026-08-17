"""Las partes de `silver` que no necesitan Spark."""

import pytest

from acervo_transform import silver


@pytest.mark.parametrize("mes", ["2024-01", "2009-12", "2024-10"])
def test_meses_validos(mes):
    silver.validar_mes(mes)


@pytest.mark.parametrize("mes", ["2024-1", "2024-13", "2024-00", "enero", "2024/01", ""])
def test_meses_invalidos(mes):
    with pytest.raises(silver.MesInvalido):
        silver.validar_mes(mes)


def test_la_ruta_de_raw_coincide_con_donde_escribe_ingest():
    assert silver.ruta_raw("raw", "yellow", "2024-01") == "s3a://raw/tlc/yellow/2024-01.parquet"


def test_la_tabla_lleva_el_servicio_en_el_nombre():
    """Para que green y fhvhv entren sin reestructurar."""
    assert silver.nombre_tabla("acervo", "yellow") == "acervo.silver.tlc_yellow"
    assert silver.nombre_tabla("acervo", "green") == "acervo.silver.tlc_green"


def test_el_informe_detecta_la_postcondicion_rota():
    base = dict(tabla="t", mes="2024-01", marcadas=0, sobrantes=(), tabla_creada=False)
    assert silver.Informe(leidas=100, escritas=100, **base).coherente
    assert not silver.Informe(leidas=100, escritas=99, **base).coherente
