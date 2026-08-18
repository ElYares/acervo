"""CU-003: el primer mart de gold, viajes por zona de recogida y hora.

Requieren `devherd up` y `acervo.silver.tlc_yellow` materializada.

**La prueba que mas vale aqui es la primera**, y no es sobre numeros. La lista de
banderas vive dos veces —en `calidad.BANDERAS` y en los `vars` de
`dbt_project.yml`— porque dbt no puede importar Python. Si se separan, gold
filtra por una lista vieja y **nada falla**: el mart sale, los conteos cambian y
nadie mira. Todo lo demas de este archivo comprueba resultados; esa comprueba
que las dos copias no se hayan ido cada una por su lado.
"""

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from acervo_transform import calidad, silver
from acervo_transform.config import SparkConfig

pytestmark = pytest.mark.integracion

RAIZ = Path(__file__).resolve().parent.parent
DBT = Path(sys.executable).parent / "dbt"

MES = "2024-01"
MODELO = "viajes_por_zona_hora"

# Medidos sobre yellow 2024-01. Si el codigo deja de reproducirlos, o cambio una
# regla o se rompio algo: en los dos casos hay que mirarlo.
FILAS_MART = 5_128
VIAJES = 2_840_426
INGRESO = Decimal("77673581.13")
DISTANCIA = 9_368_548.63
ZONAS = 257


@pytest.fixture(scope="module")
def spark():
    try:
        sesion = silver.sesion(SparkConfig.desde_entorno())
        sesion.sql("SELECT 1").collect()
    except Exception as err:  # noqa: BLE001 - cualquier fallo aqui es "no hay stack"
        pytest.skip(f"Spark Connect no responde; levanta el stack con `devherd up`: {err}")
    yield sesion
    sesion.stop()


@pytest.fixture(scope="module")
def catalogo(spark):
    return SparkConfig.desde_entorno().catalogo


@pytest.fixture(scope="module")
def tabla(catalogo):
    return f"{catalogo}.gold.{MODELO}"


@pytest.fixture(scope="module")
def mart(spark, catalogo, tabla):
    """Materializa el mart una vez y lo comparte con las pruebas."""
    if not spark.catalog.tableExists(f"{catalogo}.silver.tlc_yellow"):
        pytest.skip("silver no esta materializada; corre `uv run silver tlc yellow --mes ...`")

    proceso = subprocess.run(
        [str(DBT), "run", "--select", MODELO],
        cwd=RAIZ, capture_output=True, text=True, timeout=600,
    )
    assert proceso.returncode == 0, proceso.stdout
    return spark.table(tabla)


def test_las_banderas_de_dbt_son_las_de_silver():
    """La unica copia de `calidad.BANDERAS` fuera de Python no puede divergir.

    Si esta prueba falla despues de tocar `calidad.py`, la correccion **no** es
    editar la prueba: es actualizar los `vars` de `dbt_project.yml`. Gold estaba
    filtrando por una lista que ya no existe.
    """
    proyecto = yaml.safe_load((RAIZ / "dbt_project.yml").read_text())
    declaradas = proyecto["vars"]["banderas_calidad"]
    assert declaradas == [b.nombre for b in calidad.BANDERAS]


def test_el_mart_tiene_las_filas_del_perfilado(mart):
    assert mart.count() == FILAS_MART


def test_descarta_exactamente_lo_que_silver_marco(spark, mart, catalogo, tabla):
    """Contra silver, no contra una constante.

    Una constante solo dice que el numero no cambio. Esto dice que gold y silver
    siguen de acuerdo sobre que es una fila limpia, que es la propiedad real.
    """
    limpias = spark.sql(f"""
        SELECT count(*) FROM {catalogo}.silver.tlc_yellow
        WHERE NOT ({calidad.condicion_marcada()})
    """).collect()[0][0]

    viajes = spark.sql(f"SELECT sum(viajes) FROM {tabla}").collect()[0][0]
    assert viajes == limpias == VIAJES


def test_el_ingreso_cuadra_y_no_es_coma_flotante(spark, mart, tabla):
    fila = spark.sql(f"SELECT sum(ingreso) i, round(sum(distancia_total), 2) d FROM {tabla}")
    resultado = fila.collect()[0]
    assert resultado["i"] == INGRESO
    assert resultado["d"] == DISTANCIA

    # decimal y no double: sumar millones de double acumula error. Decision 006.
    assert dict(mart.dtypes)["ingreso"].startswith("decimal")


def test_cubre_las_zonas_y_las_horas_del_origen(spark, tabla):
    fila = spark.sql(f"""
        SELECT count(DISTINCT pu_location_id) z, count(DISTINCT hora) h,
               min(hora) mn, max(hora) mx
        FROM {tabla}
    """).collect()[0]
    assert fila["z"] == ZONAS
    assert (fila["h"], fila["mn"], fila["mx"]) == (24, 0, 23)


def test_el_grano_no_se_duplica(spark, tabla):
    duplicados = spark.sql(f"""
        SELECT count(*) FROM (
            SELECT mes, pu_location_id, hora FROM {tabla}
            GROUP BY mes, pu_location_id, hora HAVING count(*) > 1
        )
    """).collect()[0][0]
    assert duplicados == 0


def test_esta_particionado_por_mes(spark, mart, tabla):
    """Sin particion por mes, el backfill de varios meses reescribe el historico."""
    particiones = spark.sql(f"SELECT partition.mes, record_count FROM {tabla}.partitions").collect()
    assert [(f[0], f[1]) for f in particiones] == [(MES, FILAS_MART)]


def test_rematerializar_no_cambia_los_conteos(spark, mart, tabla):
    consulta = f"SELECT count(*) c, sum(viajes) v, sum(ingreso) i FROM {tabla}"
    antes = spark.sql(consulta).collect()[0]

    proceso = subprocess.run(
        [str(DBT), "run", "--select", MODELO],
        cwd=RAIZ, capture_output=True, text=True, timeout=600,
    )
    assert proceso.returncode == 0, proceso.stdout

    consulta = f"SELECT count(*) c, sum(viajes) v, sum(ingreso) i FROM {tabla}"
    despues = spark.sql(consulta).collect()[0]
    assert (despues["c"], despues["v"], despues["i"]) == (antes["c"], antes["v"], antes["i"])


def test_las_pruebas_de_dbt_pasan(mart):
    """Incluye E1: un mart vacio falla en vez de salir en verde."""
    proceso = subprocess.run(
        [str(DBT), "test", "--select", MODELO],
        cwd=RAIZ, capture_output=True, text=True, timeout=600,
    )
    assert proceso.returncode == 0, proceso.stdout
    assert "Completed successfully" in proceso.stdout
