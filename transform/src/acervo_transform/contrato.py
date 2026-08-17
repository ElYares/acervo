"""El contrato de columnas de silver: que entra, con que nombre y de que tipo.

Esta tabla es la que hace verificable a E2 de CU-002. Sin ella, un mes con el
esquema cambiado falla con "no se pudo leer" y no dice que columna falto, que es
justo lo inutil: TLC no publica el mismo esquema en 2009 y en 2024.

La regla de nombres es la que ya sigue `ingest`: **ingles para lo que nombra la
TLC, espanol para lo que nombra acervo**. Por eso las 19 columnas de origen
conservan el vocabulario del diccionario oficial y `mes` y las banderas de
`calidad.py` van en espanol.
"""

from collections.abc import Iterable
from dataclasses import dataclass

# El nombre de la particion. Es vocabulario de acervo, no de TLC.
PARTICION = "mes"


@dataclass(frozen=True)
class Columna:
    """Una columna del origen y su forma en silver."""

    origen: str
    silver: str
    tipo: str


@dataclass(frozen=True)
class Resuelta(Columna):
    """Una columna del contrato ya localizada en un DataFrame concreto.

    `hallada` es el nombre **real** que traia el archivo, que puede diferir de
    `origen` en mayusculas. Es el que hay que usar para leer.
    """

    hallada: str


# Los importes van a decimal(10,2) y no se quedan en double: sumar millones de
# double en gold acumula error de coma flotante, y los importes de TLC son de
# dos decimales por construccion. Los enteros se unifican en int aunque el
# origen mezcle int y bigint, para que el dia que entre `green` con anchos
# distintos la union en gold no degenere.
_YELLOW = (
    Columna("VendorID", "vendor_id", "int"),
    # Sin el prefijo `tpep_`: es especifico de yellow y `green` usa `lpep_`.
    # Conservarlo obligaria a que tlc_green nombrara distinto la misma cosa.
    Columna("tpep_pickup_datetime", "pickup_datetime", "timestamp_ntz"),
    Columna("tpep_dropoff_datetime", "dropoff_datetime", "timestamp_ntz"),
    Columna("passenger_count", "passenger_count", "int"),
    Columna("trip_distance", "trip_distance", "double"),
    Columna("RatecodeID", "ratecode_id", "int"),
    # Se queda string: pasar 'Y'/'N' a booleano convertiria en null cualquier
    # valor inesperado, y silver no pierde informacion. Que gold decida.
    Columna("store_and_fwd_flag", "store_and_fwd_flag", "string"),
    Columna("PULocationID", "pu_location_id", "int"),
    Columna("DOLocationID", "do_location_id", "int"),
    Columna("payment_type", "payment_type", "int"),
    Columna("fare_amount", "fare_amount", "decimal(10,2)"),
    Columna("extra", "extra", "decimal(10,2)"),
    Columna("mta_tax", "mta_tax", "decimal(10,2)"),
    Columna("tip_amount", "tip_amount", "decimal(10,2)"),
    Columna("tolls_amount", "tolls_amount", "decimal(10,2)"),
    Columna("improvement_surcharge", "improvement_surcharge", "decimal(10,2)"),
    Columna("total_amount", "total_amount", "decimal(10,2)"),
    Columna("congestion_surcharge", "congestion_surcharge", "decimal(10,2)"),
    Columna("Airport_fee", "airport_fee", "decimal(10,2)"),
)

# Un contrato por servicio. `green`, `fhv` y `fhvhv` entran agregando su tupla,
# no reestructurando: es la razon de que la tabla se llame `tlc_<servicio>`.
CONTRATOS: dict[str, tuple[Columna, ...]] = {"yellow": _YELLOW}


class ServicioSinContrato(ValueError):
    """El servicio existe en TLC pero todavia no tiene contrato escrito."""


class EsquemaInvalido(ValueError):
    """Al origen le faltan columnas del contrato. Dice cuales."""


@dataclass(frozen=True)
class Resolucion:
    columnas: tuple[Resuelta, ...]
    sobrantes: tuple[str, ...]


def contrato(servicio: str) -> tuple[Columna, ...]:
    try:
        return CONTRATOS[servicio]
    except KeyError as err:
        conocidos = ", ".join(sorted(CONTRATOS))
        raise ServicioSinContrato(
            f"no hay contrato de columnas para '{servicio}'; hoy solo: {conocidos}"
        ) from err


def resolver(servicio: str, campos: Iterable[str]) -> Resolucion:
    """Localiza cada columna del contrato entre los campos del archivo.

    El emparejado ignora mayusculas. El origen ya mezcla cuatro convenciones en
    el mismo archivo (`VendorID`, `tpep_pickup_datetime`, `PULocationID`,
    `Airport_fee`), asi que un cambio de caja entre meses es plausible y no
    deberia parecerse a una columna que falta.

    Falla nombrando **todas** las que faltan, no la primera: con un esquema
    viejo faltan varias y descubrirlas de a una es un ciclo inutil.
    """
    reales = list(campos)
    por_minuscula = {c.lower(): c for c in reales}

    columnas: list[Resuelta] = []
    faltantes: list[str] = []
    for col in contrato(servicio):
        hallada = por_minuscula.get(col.origen.lower())
        if hallada is None:
            faltantes.append(col.origen)
        else:
            columnas.append(
                Resuelta(origen=col.origen, silver=col.silver, tipo=col.tipo, hallada=hallada)
            )

    if faltantes:
        raise EsquemaInvalido(
            f"al origen de '{servicio}' le faltan {len(faltantes)} columnas del contrato: "
            + ", ".join(faltantes)
        )

    esperadas = {c.origen.lower() for c in contrato(servicio)}
    sobrantes = tuple(sorted(c for c in reales if c.lower() not in esperadas))
    return Resolucion(columnas=tuple(columnas), sobrantes=sobrantes)
