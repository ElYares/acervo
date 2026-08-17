"""Pruebas contra el stack real: Spark Connect, Nessie y MinIO.

Requieren `devherd up` y el mes en `raw/`. Sin eso, se saltan.

Lo que se prueba aqui no se puede probar con mocks sin reimplementar Iceberg:
que reemplazar la particion no acumule filas, que la particion tenga tantas
filas que el origen y que las banderas cuenten lo que dijo el perfilado.

Son dos materializaciones de casi tres millones de filas: tarda alrededor de un
minuto.
"""

import pytest

from acervo_transform import calidad, silver
from acervo_transform.config import SparkConfig

pytestmark = pytest.mark.integracion

MES = "2024-01"
SERVICIO = "yellow"

# Conteos del perfilado de yellow 2024-01. Si el codigo deja de reproducirlos,
# o cambio una regla o se rompio algo: en los dos casos hay que mirarlo.
FILAS = 2_964_624
MARCADAS = 124_198
POR_BANDERA = {
    "fuera_de_mes": 18,
    "cronologia_invalida": 870,
    "duracion_absurda": 16,
    "sin_distancia": 60_371,
    "velocidad_absurda": 1_024,
    "importe_negativo": 35_504,
    "pasajeros_cero": 31_465,
}


@pytest.fixture(scope="module")
def cfg():
    return SparkConfig.desde_entorno()


@pytest.fixture(scope="module")
def spark(cfg):
    try:
        sesion = silver.sesion(cfg)
        sesion.sql("SELECT 1").collect()
    except Exception as err:  # noqa: BLE001 - cualquier fallo aqui es "no hay stack"
        pytest.skip(f"Spark Connect no responde; levanta el stack con `devherd up`: {err}")
    yield sesion
    sesion.stop()


@pytest.fixture(scope="module")
def informe(spark, cfg):
    """Materializa el mes una vez y comparte el resultado con las pruebas."""
    try:
        return silver.materializar(spark, cfg, SERVICIO, MES)
    except silver.MesNoEstaEnRaw as err:
        pytest.skip(str(err))


def test_no_pierde_filas(informe):
    """La postcondicion de CU-002."""
    assert informe.leidas == FILAS
    assert informe.escritas == FILAS
    assert informe.coherente


def test_marca_sin_descartar(informe):
    assert informe.marcadas == MARCADAS
    assert informe.marcadas < informe.escritas


def test_el_contrato_cubre_el_origen_entero(informe):
    """Si el origen trae columnas nuevas, esto lo delata en vez de ignorarlas
    en silencio."""
    assert informe.sobrantes == ()


def test_cada_bandera_cuenta_lo_que_dijo_el_perfilado(spark, informe):
    cols = ", ".join(f"sum(cast({b} as long)) as {b}" for b in POR_BANDERA)
    fila = spark.sql(f"SELECT {cols} FROM {informe.tabla} WHERE mes = '{MES}'").collect()[0]
    assert {b: fila[b] for b in POR_BANDERA} == POR_BANDERA


def test_ninguna_bandera_queda_nula(spark, informe):
    """Una bandera nula no esta ni marcada ni limpia, y gold la perderia."""
    nulos = " + ".join(f"sum(cast({b} is null as long))" for b in POR_BANDERA)
    assert spark.sql(f"SELECT {nulos} AS n FROM {informe.tabla}").collect()[0]["n"] == 0


def test_la_particion_es_el_mes_del_archivo_y_no_la_recogida(spark, informe):
    """Las 18 filas con recogida fuera del mes se quedan en la particion.

    Si la particion se derivara de `pickup_datetime`, se irian a otros meses y
    la particion tendria menos filas que el origen.
    """
    fuera = spark.sql(
        f"SELECT count(*) AS n FROM {informe.tabla} "
        f"WHERE mes = '{MES}' AND date_format(pickup_datetime, 'yyyy-MM') <> '{MES}'"
    ).collect()[0]["n"]
    assert fuera == POR_BANDERA["fuera_de_mes"]


def test_rematerializar_reemplaza_y_no_acumula(spark, cfg, informe):
    """A1: es lo que hace re-ejecutable el paso.

    Sin esto, un reintento tras un fallo a la mitad duplica el mes entero y
    nadie se entera hasta gold.
    """
    segundo = silver.materializar(spark, cfg, SERVICIO, MES)
    assert segundo.escritas == informe.escritas
    assert segundo.marcadas == informe.marcadas
    assert not segundo.tabla_creada


def test_un_mes_que_no_esta_en_raw_no_crea_particion_vacia(spark, cfg):
    """E1: una particion vacia es indistinguible de 'ese mes no tuvo viajes'."""
    with pytest.raises(silver.MesNoEstaEnRaw):
        silver.materializar(spark, cfg, SERVICIO, "2099-01")

    tabla = silver.nombre_tabla(cfg.catalogo, SERVICIO)
    meses = [r["mes"] for r in spark.sql(f"SELECT DISTINCT mes FROM {tabla}").collect()]
    assert "2099-01" not in meses


def test_las_banderas_de_la_tabla_son_las_declaradas(spark, informe):
    columnas = set(spark.table(informe.tabla).columns)
    assert {b.nombre for b in calidad.BANDERAS} <= columnas
