import pytest

from acervo_ingest import tlc

# La base entra por parametro, asi que estas pruebas no necesitan entorno ni
# conocen el origen real.
BASE = "https://origen.invalido/trip-data"


def test_url_del_mes():
    assert tlc.url_mes(BASE, "yellow", "2024-01") == f"{BASE}/yellow_tripdata_2024-01.parquet"


def test_la_base_sale_de_la_configuracion():
    assert tlc.url_mes("http://otro/datos", "yellow", "2024-01").startswith("http://otro/datos/")


def test_key_deja_lugar_a_otros_servicios():
    assert tlc.key_destino("yellow", "2024-01") == "tlc/yellow/2024-01.parquet"
    assert tlc.key_destino("fhvhv", "2024-01") == "tlc/fhvhv/2024-01.parquet"


@pytest.mark.parametrize("mes", ["2024-1", "2024-13", "2024-00", "202401", "enero", ""])
def test_mes_mal_formado_se_rechaza(mes):
    with pytest.raises(tlc.MesInvalido):
        tlc.url_mes(BASE, "yellow", mes)


def test_servicio_desconocido_se_rechaza():
    with pytest.raises(tlc.ServicioInvalido):
        tlc.url_mes(BASE, "morado", "2024-01")
