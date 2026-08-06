"""Materializa un mes de raw como particion de una tabla Iceberg silver.

Implementa CU-002. Las tres propiedades que lo definen:

- **Re-ejecutable.** La particion del mes se reemplaza entera, nunca se acumula.
  Un reintento tras un fallo a la mitad no duplica el mes
- **Atomica.** `overwritePartitions()` es un unico commit de Iceberg: la
  particion queda completa o como estaba. Verificado contra el stack, no
  deducido; el detalle esta en E3 de CU-002
- **Sin perdida.** No filtra nada: marca con las banderas de `calidad.py` y
  deja que gold decida
"""

import re
from dataclasses import dataclass

from pyspark.errors import AnalysisException
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from acervo_transform import calidad, contrato
from acervo_transform.config import SparkConfig
from acervo_transform.contrato import PARTICION

_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Marcadores con los que Spark reporta una ruta inexistente. Se distinguen del
# resto de errores de analisis para no disfrazar un fallo real de permisos o de
# esquema como "corre ingest primero".
_NO_EXISTE = ("PATH_NOT_FOUND", "Path does not exist", "FileNotFoundException")


class MesInvalido(ValueError):
    pass


class MesNoEstaEnRaw(RuntimeError):
    """El objeto no esta en raw. No se crea tabla ni particion vacia."""


@dataclass(frozen=True)
class Informe:
    tabla: str
    mes: str
    leidas: int
    marcadas: int
    escritas: int
    sobrantes: tuple[str, ...]
    tabla_creada: bool

    @property
    def coherente(self) -> bool:
        """La postcondicion de CU-002: la particion tiene tantas filas que el origen."""
        return self.leidas == self.escritas


def validar_mes(mes: str) -> None:
    if not _MES.match(mes):
        raise MesInvalido(f"mes '{mes}' no tiene formato YYYY-MM")


def ruta_raw(bucket: str, servicio: str, mes: str) -> str:
    """La ruta del parquet del mes. Pura: el bucket entra por parametro."""
    validar_mes(mes)
    return f"s3a://{bucket}/tlc/{servicio}/{mes}.parquet"


def nombre_tabla(catalogo: str, servicio: str) -> str:
    """`tlc_<servicio>` para que green y fhvhv entren sin reestructurar."""
    return f"{catalogo}.silver.tlc_{servicio}"


def sesion(cfg: SparkConfig) -> SparkSession:
    return SparkSession.builder.remote(cfg.remote).getOrCreate()


def _leer(spark: SparkSession, ruta: str) -> DataFrame:
    """Lee el parquet del mes y **fuerza el analisis del esquema**.

    Con Spark Connect `read.parquet` no toca la red: es perezoso. Sin pedir el
    esquema aqui, una ruta inexistente no falla en este `try` sino mucho
    despues, la primera vez que alguien mira las columnas, y E1 degenera en un
    traceback de gRPC en vez del mensaje que dice que hay que correr `ingest`.
    """
    try:
        df = spark.read.parquet(ruta)
        _ = df.schema
        return df
    except AnalysisException as err:
        if any(marca in str(err) for marca in _NO_EXISTE):
            raise MesNoEstaEnRaw(
                f"no hay nada en {ruta}. Corre primero: cd ingest && uv run ingest tlc ..."
            ) from err
        raise


def transformar(crudo: DataFrame, servicio: str, mes: str) -> tuple[DataFrame, tuple[str, ...]]:
    """Aplica el contrato de columnas y agrega la particion y las banderas.

    Separada de la escritura a proposito: es la parte con reglas y se puede
    mirar sin escribir nada.
    """
    resolucion = contrato.resolver(servicio, crudo.columns)

    tipado = crudo.select(
        *[F.col(f"`{c.hallada}`").cast(c.tipo).alias(c.silver) for c in resolucion.columnas]
    )

    # El mes es un literal del archivo, no `date_format(pickup_datetime)`. Hay
    # filas con la recogida fuera del mes —18 en 2024-01, con relojes de 2002 y
    # 2009— y derivar la particion las mandaria a otros meses, rompiendo la
    # postcondicion de que la particion tiene tantas filas que el origen.
    con_mes = tipado.withColumn(PARTICION, F.lit(mes))

    marcado = con_mes.select(
        "*", *[F.expr(calidad.expresion(b)).alias(b.nombre) for b in calidad.BANDERAS]
    )
    return marcado, resolucion.sobrantes


def materializar(spark: SparkSession, cfg: SparkConfig, servicio: str, mes: str) -> Informe:
    validar_mes(mes)
    ruta = ruta_raw(cfg.bucket_raw, servicio, mes)
    tabla = nombre_tabla(cfg.catalogo, servicio)

    crudo = _leer(spark, ruta)
    marcado, sobrantes = transformar(crudo, servicio, mes)

    # Se cachea porque se recorre dos veces antes de escribir, y el origen esta
    # del otro lado de la red.
    marcado.cache()
    leidas = marcado.count()
    marcadas = marcado.filter(F.expr(calidad.condicion_marcada())).count()

    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {cfg.catalogo}.silver")
    existe = spark.catalog.tableExists(tabla)

    escritor = marcado.writeTo(tabla)
    if existe:
        # A1: la particion del mes se reemplaza completa. Es lo que hace el paso
        # re-ejecutable; sin esto un reintento duplicaria el mes entero.
        escritor.overwritePartitions()
    else:
        # A2: la tabla nace particionada por mes.
        escritor.partitionedBy(F.col(PARTICION)).create()

    escritas = spark.table(tabla).filter(F.col(PARTICION) == mes).count()
    marcado.unpersist()

    return Informe(
        tabla=tabla,
        mes=mes,
        leidas=leidas,
        marcadas=marcadas,
        escritas=escritas,
        sobrantes=sobrantes,
        tabla_creada=not existe,
    )
