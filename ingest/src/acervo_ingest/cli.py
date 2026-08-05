"""Entrada de usuario."""

from typing import Annotated

import typer

from acervo_ingest import tlc
from acervo_ingest.config import ErrorConfiguracion, OrigenTLC
from acervo_ingest.storage import ErrorAlmacenamiento, almacen_raw

app = typer.Typer(
    name="ingest",
    help="Descarga incremental de fuentes publicas a la capa raw.",
    no_args_is_help=True,
    add_completion=False,
)

@app.callback()
def principal() -> None:
    """Existe para que `tlc` siga siendo subcomando.

    Con un solo comando registrado, typer colapsa el grupo y la invocacion
    pasaria a ser `ingest yellow`. Al agregar GH Archive como comando hermano
    esto deja de hacer falta, pero el contrato de la CLI no debe cambiar por eso.
    """


_MENSAJE = {
    tlc.Resultado.DESCARGADO: "descargado",
    tlc.Resultado.YA_PRESENTE: "ya presente, no se descargo nada",
    tlc.Resultado.REVISION: "REVISION del origen, se volvio a descargar",
    tlc.Resultado.NO_DISPONIBLE: "no publicado en el origen",
}


@app.command("tlc")
def comando_tlc(
    servicio: Annotated[str, typer.Argument(help=f"Uno de: {', '.join(tlc.SERVICIOS)}")],
    mes: Annotated[str, typer.Option("--mes", help="Mes en formato YYYY-MM")],
    forzar: Annotated[bool, typer.Option("--forzar", help="Descarga aunque ya este")] = False,
) -> None:
    """Ingiere un mes de TLC a la capa raw."""
    # La configuracion se resuelve entera antes de tocar la red: si falta una
    # variable, el fallo no puede aparecer a media descarga.
    try:
        almacen = almacen_raw()
        origen = OrigenTLC.desde_entorno()
    except ErrorConfiguracion as err:
        typer.secho(f"configuracion: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(3) from err

    try:
        informe = tlc.ingerir(almacen, origen, servicio, mes, forzar=forzar)
    except (tlc.MesInvalido, tlc.ServicioInvalido) as err:
        typer.secho(str(err), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from err
    except ErrorAlmacenamiento as err:
        typer.secho(f"destino: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from err

    detalle = f"  {informe.bytes / 1048576:.1f} MB" if informe.bytes else ""
    typer.echo(f"{informe.key}  {_MENSAJE[informe.resultado]}{detalle}")

    # Un mes no publicado no es un fallo: en un backfill es la senal de que se
    # llego al final, y salir con error haria reintentar para siempre.
