"""El nucleo de descarga, probado sin red ni MinIO.

Lo que mas importa aqui es `ausente_en`: es lo unico que convierte una respuesta
de error del origen en un final feliz, y su default vacio es lo que impide que
una fuente herede en silencio el "no publicado" de otra.
"""

import httpx
import pytest

from acervo_ingest import descarga
from acervo_ingest.descarga import ErrorOrigen, Resultado

URL = "https://origen.invalido/archivo.csv"
KEY = "prueba/archivo.csv"
CUERPO = b'"LocationID","Zone"\n132,"JFK Airport"\n'


class AlmacenFalso:
    """Lo minimo de `AlmacenRaw` que toca `descargar_si_cambio`."""

    def __init__(self, etags: dict[str, str] | None = None):
        self.etags = dict(etags or {})
        self.subidas: list[tuple[str, bytes, str]] = []

    def etag_registrado(self, key: str) -> str | None:
        return self.etags.get(key)

    def subir(self, key, cuerpo, etag_origen, tamano_esperado) -> None:
        datos = cuerpo.read(-1)
        assert len(datos) == tamano_esperado, "el nucleo declaro un tamano que no entrego"
        self.subidas.append((key, datos, etag_origen))
        self.etags[key] = etag_origen


@pytest.fixture
def origen(monkeypatch):
    """Instala un origen HTTP simulado. Devuelve la lista de peticiones hechas."""

    def instalar(
        status: int = 200,
        cuerpo: bytes = CUERPO,
        etag: str = "abc",
        con_tamano: bool = True,
    ) -> list[httpx.Request]:
        pedidos: list[httpx.Request] = []
        cabeceras = {"etag": f'"{etag}"'}
        if con_tamano:
            cabeceras["content-length"] = str(len(cuerpo))

        def responder(peticion: httpx.Request) -> httpx.Response:
            pedidos.append(peticion)
            if peticion.method == "HEAD":
                return httpx.Response(status, headers=cabeceras)
            return httpx.Response(status, headers=cabeceras, content=cuerpo)

        transporte = httpx.MockTransport(responder)
        real = httpx.Client
        monkeypatch.setattr(
            descarga.httpx,
            "Client",
            lambda **kw: real(**kw, transport=transporte),
        )
        return pedidos

    return instalar


class TestPoliticaDeAusencia:
    """La diferencia entre los viajes y el catalogo vive entera en un parametro."""

    def test_sin_ausente_en_un_403_es_un_fallo(self, origen):
        origen(status=403)
        almacen = AlmacenFalso()

        with pytest.raises(ErrorOrigen, match="403"):
            descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert almacen.subidas == [], "no debe escribir nada si el origen fallo"

    def test_con_ausente_en_un_403_es_no_disponible(self, origen):
        origen(status=403)

        informe = descarga.descargar_si_cambio(
            AlmacenFalso(), URL, KEY, timeout=1.0, ausente_en=(403, 404)
        )

        assert informe.resultado is Resultado.NO_DISPONIBLE

    def test_el_default_no_perdona_ningun_codigo(self):
        # Si alguien le pone un default no vacio, el catalogo de zonas empieza a
        # tratar un origen caido como "no publicado" y se queda sin datos en
        # silencio. Esta prueba existe para que ese cambio duela.
        import inspect

        firma = inspect.signature(descarga.descargar_si_cambio)
        assert firma.parameters["ausente_en"].default == ()

    def test_un_500_es_fallo_aunque_se_perdonen_los_403(self, origen):
        origen(status=500)

        with pytest.raises(ErrorOrigen, match="500"):
            descarga.descargar_si_cambio(
                AlmacenFalso(), URL, KEY, timeout=1.0, ausente_en=(403, 404)
            )


class TestMarcaDeAgua:
    def test_sin_marca_previa_descarga(self, origen):
        pedidos = origen()
        almacen = AlmacenFalso()

        informe = descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert informe.resultado is Resultado.DESCARGADO
        assert informe.bytes == len(CUERPO)
        assert informe.etag == "abc"
        assert [p.method for p in pedidos] == ["HEAD", "GET"]

    def test_el_cuerpo_llega_intacto(self, origen):
        origen()
        almacen = AlmacenFalso()

        descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert almacen.subidas == [(KEY, CUERPO, "abc")]

    def test_marca_igual_no_descarga(self, origen):
        pedidos = origen(etag="abc")
        almacen = AlmacenFalso({KEY: "abc"})

        informe = descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert informe.resultado is Resultado.YA_PRESENTE
        assert [p.method for p in pedidos] == ["HEAD"], (
            "el GET sobra: eso es lo que hace incremental a esto"
        )
        assert almacen.subidas == []

    def test_marca_distinta_es_revision(self, origen):
        origen(etag="nuevo")
        almacen = AlmacenFalso({KEY: "viejo"})

        informe = descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert informe.resultado is Resultado.REVISION
        assert almacen.etags[KEY] == "nuevo"

    def test_forzar_descarga_aunque_la_marca_coincida(self, origen):
        pedidos = origen(etag="abc")
        almacen = AlmacenFalso({KEY: "abc"})

        informe = descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0, forzar=True)

        assert informe.resultado is Resultado.DESCARGADO
        assert [p.method for p in pedidos] == ["HEAD", "GET"]


class TestTransporteSinComprimir:
    """La trampa que solo revelo el CSV.

    CloudFront comprime lo comprimible y, cuando lo hace, omite
    `Content-Length`. httpx ademas descomprime `iter_bytes()` de forma
    transparente, asi que los bytes que subiriamos no serian los que el header
    describe: `raw/` dejaria de ser fiel al origen y la verificacion
    anti-parcial compararia tamanos de cosas distintas.

    El parquet de los viajes nunca lo revelo porque ya es binario comprimido y
    CloudFront lo deja pasar sin tocar.
    """

    def test_se_pide_el_cuerpo_sin_comprimir(self, origen):
        pedidos = origen()

        descarga.descargar_si_cambio(AlmacenFalso(), URL, KEY, timeout=1.0)

        assert pedidos, "no se hizo ninguna peticion"
        for peticion in pedidos:
            assert peticion.headers["accept-encoding"] == "identity", (
                "con gzip el origen omite Content-Length y httpx descomprime solo"
            )

    def test_sin_content_length_no_se_descarga_nada(self, origen):
        almacen = AlmacenFalso()
        origen(con_tamano=False)

        with pytest.raises(ErrorOrigen, match="Content-Length"):
            descarga.descargar_si_cambio(almacen, URL, KEY, timeout=1.0)

        assert almacen.subidas == [], (
            "sin tamano declarado no hay como verificar que la descarga sea "
            "completa, y un objeto parcial en raw/ se da por bueno para siempre"
        )


class TestLectorStream:
    def test_lee_por_partes_sin_materializar(self):
        lector = descarga._LectorStream(iter([b"abc", b"def", b"ghi"]))
        assert lector.read(4) == b"abcd"
        assert lector.read(4) == b"efgh"
        assert lector.read(4) == b"i"
        assert lector.read(4) == b""

    def test_lee_todo_con_n_negativo(self):
        lector = descarga._LectorStream(iter([b"abc", b"def"]))
        assert lector.read(-1) == b"abcdef"

    def test_respeta_los_limites_de_los_trozos(self):
        # boto3 pide bloques grandes; el lector no debe perder bytes al cruzar
        # la frontera entre dos trozos del stream.
        trozos = [b"x" * 7, b"y" * 5, b"z" * 3]
        lector = descarga._LectorStream(iter(trozos))
        assert lector.read(100) == b"x" * 7 + b"y" * 5 + b"z" * 3
