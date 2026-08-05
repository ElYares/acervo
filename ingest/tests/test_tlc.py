import pytest

from acervo_ingest import tlc


def test_url_del_mes():
    assert tlc.url_mes("yellow", "2024-01").endswith("/yellow_tripdata_2024-01.parquet")


def test_key_deja_lugar_a_otros_servicios():
    assert tlc.key_destino("yellow", "2024-01") == "tlc/yellow/2024-01.parquet"
    assert tlc.key_destino("fhvhv", "2024-01") == "tlc/fhvhv/2024-01.parquet"


@pytest.mark.parametrize("mes", ["2024-1", "2024-13", "2024-00", "202401", "enero", ""])
def test_mes_mal_formado_se_rechaza(mes):
    with pytest.raises(tlc.MesInvalido):
        tlc.url_mes("yellow", mes)


def test_servicio_desconocido_se_rechaza():
    with pytest.raises(tlc.ServicioInvalido):
        tlc.url_mes("morado", "2024-01")


class TestLectorStream:
    def test_lee_por_partes_sin_materializar(self):
        lector = tlc._LectorStream(iter([b"abc", b"def", b"ghi"]))
        assert lector.read(4) == b"abcd"
        assert lector.read(4) == b"efgh"
        assert lector.read(4) == b"i"
        assert lector.read(4) == b""

    def test_lee_todo_con_n_negativo(self):
        lector = tlc._LectorStream(iter([b"abc", b"def"]))
        assert lector.read(-1) == b"abcdef"

    def test_respeta_los_limites_de_los_trozos(self):
        # boto3 pide bloques grandes; el lector no debe perder bytes al cruzar
        # la frontera entre dos trozos del stream.
        trozos = [b"x" * 7, b"y" * 5, b"z" * 3]
        lector = tlc._LectorStream(iter(trozos))
        assert lector.read(100) == b"x" * 7 + b"y" * 5 + b"z" * 3
