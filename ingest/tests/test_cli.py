"""El contrato de la CLI.

`tlc-zonas` es un comando **hermano** de `tlc`. Estas pruebas existen para que
agregarlo no le haya cambiado la forma al que ya estaba.
"""

from typer.testing import CliRunner

from acervo_ingest.cli import app

runner = CliRunner()


def test_los_dos_comandos_estan_registrados():
    salida = runner.invoke(app, ["--help"]).output

    assert "tlc" in salida
    assert "tlc-zonas" in salida


def test_tlc_conserva_su_contrato():
    salida = runner.invoke(app, ["tlc", "--help"]).output

    assert "--mes" in salida
    assert "yellow" in salida
    assert "--forzar" in salida


def test_el_catalogo_no_acepta_mes():
    # No es mensual: si algun dia acepta --mes, es que se colo el contrato de
    # los viajes donde no aplica.
    assert "--mes" not in runner.invoke(app, ["tlc-zonas", "--help"]).output

    assert runner.invoke(app, ["tlc-zonas", "--mes", "2024-01"]).exit_code != 0


def test_el_catalogo_no_se_cuela_como_servicio():
    # `ingest tlc zonas --mes ...` no debe existir: zonas no esta en SERVICIOS.
    resultado = runner.invoke(app, ["tlc", "zonas", "--mes", "2024-01"])

    assert resultado.exit_code != 0
