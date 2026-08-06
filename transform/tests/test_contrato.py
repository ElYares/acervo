"""El contrato de columnas. Puro: no necesita Spark ni el stack."""

import pytest

from acervo_transform import contrato

# El esquema real de yellow 2024-01, verificado leyendo el parquet de raw/.
CAMPOS_2024_01 = [
    "VendorID",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "RatecodeID",
    "store_and_fwd_flag",
    "PULocationID",
    "DOLocationID",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
    "Airport_fee",
]


def test_el_mes_real_resuelve_entero():
    r = contrato.resolver("yellow", CAMPOS_2024_01)
    assert len(r.columnas) == 19
    assert r.sobrantes == ()


def test_los_nombres_de_silver_no_arrastran_el_prefijo_de_yellow():
    # `tpep_` es especifico de yellow; green usa `lpep_`. Si el prefijo llegara
    # a silver, tlc_green nombraria distinto la misma cosa.
    silver = {c.silver for c in contrato.resolver("yellow", CAMPOS_2024_01).columnas}
    assert "pickup_datetime" in silver
    assert not any(n.startswith("tpep_") for n in silver)


def test_los_importes_van_a_decimal():
    por_nombre = {c.silver: c for c in contrato.resolver("yellow", CAMPOS_2024_01).columnas}
    assert por_nombre["total_amount"].tipo == "decimal(10,2)"
    assert por_nombre["airport_fee"].tipo == "decimal(10,2)"
    # Y la distancia no: no es dinero, no tiene dos decimales por construccion.
    assert por_nombre["trip_distance"].tipo == "double"


def test_el_emparejado_ignora_mayusculas():
    """Un cambio de caja en el origen no es una columna que falta."""
    campos = [c.replace("Airport_fee", "airport_fee") for c in CAMPOS_2024_01]
    r = contrato.resolver("yellow", campos)
    hallada = {c.silver: c.hallada for c in r.columnas}
    assert hallada["airport_fee"] == "airport_fee"
    assert r.sobrantes == ()


def test_si_faltan_columnas_las_nombra_todas():
    """Descubrirlas de a una es un ciclo inutil: un esquema viejo pierde varias."""
    campos = [c for c in CAMPOS_2024_01 if c not in ("Airport_fee", "congestion_surcharge")]
    with pytest.raises(contrato.EsquemaInvalido) as err:
        contrato.resolver("yellow", campos)
    assert "Airport_fee" in str(err.value)
    assert "congestion_surcharge" in str(err.value)


def test_las_columnas_de_mas_se_reportan_y_no_rompen():
    r = contrato.resolver("yellow", [*CAMPOS_2024_01, "cbd_congestion_fee"])
    assert r.sobrantes == ("cbd_congestion_fee",)
    assert len(r.columnas) == 19


def test_un_servicio_sin_contrato_dice_cuales_hay():
    with pytest.raises(contrato.ServicioSinContrato) as err:
        contrato.resolver("fhvhv", CAMPOS_2024_01)
    assert "yellow" in str(err.value)
