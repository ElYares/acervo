"""Las banderas de calidad. Puro: se mira la forma de las expresiones, no su
resultado sobre datos, que es lo que prueba `test_silver_integracion.py`."""

from acervo_transform import calidad


def test_son_siete_con_nombres_unicos():
    nombres = [b.nombre for b in calidad.BANDERAS]
    assert len(nombres) == 7
    assert len(set(nombres)) == 7


def test_toda_bandera_esta_blindada_contra_nulos():
    """Una bandera nula no esta ni marcada ni limpia.

    En gold, un `WHERE NOT sin_distancia` descartaria en silencio las filas con
    la bandera nula, que es justo lo que silver promete no hacer.
    """
    for b in calidad.BANDERAS:
        assert calidad.expresion(b).startswith("coalesce(")
        assert calidad.expresion(b).endswith(", false)")


def test_pasajeros_cero_mira_el_cero_y_no_el_null():
    """El null de passenger_count es ausencia estructural, no defecto.

    Son cinco columnas que faltan siempre juntas en el 4.73% de las filas y
    cruzan los tres VendorID. Marcarlo subiria el ruido de 4.19% a 8.11%.
    """
    b = next(b for b in calidad.BANDERAS if b.nombre == "pasajeros_cero")
    assert "= 0" in b.condicion
    assert "null" not in b.condicion.lower()


def test_fuera_de_mes_compara_contra_la_particion():
    """Comparar la recogida contra el mes derivado de ella misma es tautologico."""
    b = next(b for b in calidad.BANDERAS if b.nombre == "fuera_de_mes")
    assert b.condicion.endswith("<> mes")


def test_velocidad_absurda_se_protege_de_la_division_por_cero():
    b = next(b for b in calidad.BANDERAS if b.nombre == "velocidad_absurda")
    assert "> 0 AND" in b.condicion


def test_la_condicion_de_marcada_cubre_las_siete():
    marcada = calidad.condicion_marcada()
    for b in calidad.BANDERAS:
        assert b.nombre in marcada
