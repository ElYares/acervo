"""Las siete banderas de calidad de silver.

Silver **marca, no descarta**: descartar pierde informacion sin vuelta atras,
marcar deja que gold decida. Cada bandera es una columna booleana.

Los umbrales no son de memoria. Salen de perfilar `yellow 2024-01` (2,964,624
filas) y cada uno tiene su conteo en la nota de CU-002 y en la Decision 005. En
ese mes las siete juntas marcan el 4.19%.
"""

from dataclasses import dataclass

from acervo_transform.contrato import PARTICION

# Un taxi de Nueva York no promedia mas de 100 mph. El perfilado da p50 = 9.57 y
# p99.9 = 48.75, con un maximo de 1,443,333 por odometros rotos.
UMBRAL_MPH = 100

# 24 horas. Es el limite de lo interpretable como un viaje, no de lo posible.
UMBRAL_DURACION_SEG = 86_400

# La duracion aparece en tres banderas y no se guarda como columna: silver no
# agrega, una fila de silver es una fila del origen tipada y marcada.
_DURACION = "timestampdiff(SECOND, pickup_datetime, dropoff_datetime)"


@dataclass(frozen=True)
class Bandera:
    nombre: str
    descripcion: str
    condicion: str


BANDERAS = (
    Bandera(
        "fuera_de_mes",
        "la recogida cae fuera del mes del archivo",
        # Contra la columna de particion, que es el literal del archivo. No
        # contra el mes derivado de la propia recogida, que seria tautologico.
        f"date_format(pickup_datetime, 'yyyy-MM') <> {PARTICION}",
    ),
    Bandera(
        "cronologia_invalida",
        "la bajada no es posterior a la recogida",
        f"{_DURACION} <= 0",
    ),
    Bandera(
        "duracion_absurda",
        f"el viaje dura mas de {UMBRAL_DURACION_SEG // 3600} horas",
        f"{_DURACION} > {UMBRAL_DURACION_SEG}",
    ),
    Bandera(
        "sin_distancia",
        "el odometro no registro distancia",
        "trip_distance <= 0",
    ),
    Bandera(
        "velocidad_absurda",
        f"la velocidad implicita supera {UMBRAL_MPH} mph",
        # Solo con duracion positiva: si es cero o negativa ya lo dice
        # `cronologia_invalida`, y dividir por cero aqui no aporta nada.
        f"{_DURACION} > 0 AND trip_distance / ({_DURACION} / 3600.0) > {UMBRAL_MPH}",
    ),
    Bandera(
        "importe_negativo",
        "el importe total es un reverso, no un cobro",
        "total_amount < 0",
    ),
    Bandera(
        "pasajeros_cero",
        "el viaje declara cero pasajeros",
        # Cero, no null. El null de `passenger_count` es una ausencia
        # estructural del origen —cinco columnas que faltan siempre juntas en el
        # 4.73% de las filas— y no un defecto. Ver Decision 005.
        "passenger_count = 0",
    ),
)


def expresion(bandera: Bandera) -> str:
    """La condicion, blindada contra nulos.

    Sin el `coalesce`, una columna nula vuelve nula la bandera, y una bandera
    nula no esta ni marcada ni limpia: en gold, un `WHERE NOT sin_distancia`
    descartaria esas filas en silencio, que es exactamente lo que silver
    promete no hacer.
    """
    return f"coalesce({bandera.condicion}, false)"


def condicion_marcada() -> str:
    """Cierto si la fila viola al menos una bandera."""
    return " OR ".join(b.nombre for b in BANDERAS)
