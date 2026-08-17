"""HU-004: dbt escribe Iceberg en el catalogo hablando por Spark Connect.

Requieren `devherd up` y la tabla de silver materializada. Sin eso, se saltan.

**Por que estas pruebas existen y no basta con `dbt run`.** `dbt-spark` no
declara un metodo `connect`: solo `thrift`, `http`, `odbc` y `session`. Que esto
funcione depende de como esta escrito el metodo `session`, que pasa cada
`server_side_parameter` por `builder.config(...)` antes de `getOrCreate()`
(`dbt/adapters/spark/session.py:116-121`), lo que deja colar `spark.remote`.

Es un efecto colateral, no una capacidad soportada. Una version futura del
adaptador puede reordenar ese builder y romperlo **sin que nadie lo anuncie**,
porque nunca fue una promesa. Estas pruebas son lo que convierte ese riesgo en
un fallo ruidoso el dia que se levante el pin.

Todo aterriza en el namespace `puente`, que es desechable y se borra al
terminar. Gold no se toca.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from acervo_transform import silver
from acervo_transform.config import SparkConfig

pytestmark = pytest.mark.integracion

RAIZ = Path(__file__).resolve().parent.parent
DBT = Path(sys.executable).parent / "dbt"

NAMESPACE = "puente"
MODELO = "puente_dbt"


def _dbt(*args: str) -> subprocess.CompletedProcess:
    """Corre dbt en el directorio del proyecto y devuelve el proceso entero.

    Sin `check`: hay pruebas que necesitan mirar el codigo de salida y la salida
    de un fallo, no solo la del exito.
    """
    return subprocess.run(
        [str(DBT), *args],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=300,
    )


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
def corrida(spark, catalogo):
    """Deja el namespace sin existir, corre dbt una vez y lo limpia al final.

    Borrar **antes** es lo que hace verificable que dbt crea el namespace solo:
    si quedara de una corrida anterior, la prueba pasaria sin probar nada.
    """
    if not spark.catalog.tableExists(f"{catalogo}.silver.tlc_yellow"):
        pytest.skip("silver no esta materializada; corre `uv run silver tlc yellow --mes ...`")

    spark.sql(f"DROP TABLE IF EXISTS {catalogo}.{NAMESPACE}.{MODELO}")
    spark.sql(f"DROP NAMESPACE IF EXISTS {catalogo}.{NAMESPACE}")
    namespaces_antes = {f.name for f in spark.catalog.listDatabases()}

    proceso = _dbt("run", "--select", MODELO)

    yield proceso, namespaces_antes

    spark.sql(f"DROP TABLE IF EXISTS {catalogo}.{NAMESPACE}.{MODELO}")
    spark.sql(f"DROP NAMESPACE IF EXISTS {catalogo}.{NAMESPACE}")


@pytest.fixture(scope="module")
def propiedades(spark, corrida, catalogo):
    """`describe extended` como diccionario."""
    filas = spark.sql(f"DESCRIBE EXTENDED {catalogo}.{NAMESPACE}.{MODELO}").collect()
    return {f[0]: f[1] for f in filas}


def test_dbt_debug_pasa(spark):
    proceso = _dbt("debug")
    assert proceso.returncode == 0, proceso.stdout
    assert "All checks passed" in proceso.stdout


def test_la_sesion_es_remota_y_no_una_spark_local(spark):
    """Reproduce la cadena de `session.py:116-121` y comprueba que sale remota.

    Es la prueba del mecanismo entero: si un dia `builder.config('spark.remote')`
    deja de convertir la sesion en remota, dbt levantaria una Spark local en el
    proceso de pytest —lenta, sin catalogo y sin credenciales— en vez de fallar.
    Un modo de fallo silencioso es justo lo que hay que hacer ruidoso.
    """
    from pyspark.sql import SparkSession

    builder = SparkSession.builder.enableHiveSupport()
    for parametro, valor in {"spark.remote": SparkConfig.desde_entorno().remote}.items():
        builder = builder.config(parametro, valor)
    sesion = builder.getOrCreate()

    assert type(sesion).__module__ == "pyspark.sql.connect.session"


def test_el_modelo_corre_sin_error(corrida):
    proceso, _ = corrida
    assert proceso.returncode == 0, proceso.stdout
    assert "Completed successfully" in proceso.stdout


def test_la_tabla_es_iceberg_y_no_el_parquet_por_defecto(propiedades):
    assert propiedades["Provider"] == "iceberg"
    assert "format-version=2" in propiedades["Table Properties"]


def test_el_commit_quedo_en_nessie(propiedades):
    """Sin esto la tabla podria ser Iceberg y estar fuera del catalogo versionado."""
    assert "nessie.commit.id=" in propiedades["Table Properties"]


def test_un_solo_snapshot_y_es_overwrite(spark, corrida, catalogo):
    filas = spark.sql(
        f"SELECT operation FROM {catalogo}.{NAMESPACE}.{MODELO}.snapshots"
    ).collect()
    assert [f[0] for f in filas] == ["overwrite"]


def test_dbt_crea_el_namespace_solo(spark, corrida, catalogo):
    _, namespaces_antes = corrida
    assert NAMESPACE not in namespaces_antes
    assert NAMESPACE in {f.name for f in spark.catalog.listDatabases()}


def test_escribe_en_el_warehouse_sin_recibir_credenciales(propiedades):
    """El `profiles.yml` no lleva secretos y aun asi la tabla aterriza en MinIO.

    Es la misma promesa que `config.py`: este servicio no toca el object store,
    se lo pide a Spark. Si algun dia hiciera falta una clave aqui, seria senal de
    que se esta saltando el servidor.
    """
    perfil = (RAIZ / "profiles.yml").read_text().lower()
    for secreto in ("access_key", "secret_key", "minio_root", "aws_access", "aws_secret"):
        assert secreto not in perfil

    assert propiedades["Location"].startswith("s3://warehouse/")


def test_la_version_del_adaptador_esta_clavada():
    """El pin no es estetica: es lo unico que sostiene un camino no soportado."""
    from dbt.adapters.spark.connections import SparkConnectionMethod

    # Si algun dia esto falla, el adaptador gano soporte oficial de Connect y
    # media docena de comentarios de este repo se pueden borrar.
    assert not hasattr(SparkConnectionMethod, "CONNECT")

    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text())
    declaradas = pyproject["project"]["dependencies"]
    assert any(d.startswith("dbt-spark==") for d in declaradas), declaradas
