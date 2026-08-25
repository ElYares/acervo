"""Entrada de usuario."""

from typing import Annotated

import typer

from acervo_ingest import tlc, zonas
from acervo_ingest.config import ErrorConfiguracion, OrigenTLC, OrigenZonasTLC
from acervo_ingest.descarga import ErrorOrigen, Informe, Resultado
from acervo_ingest.storage import ErrorAlmacenamiento, almacen_raw

app = typer.Typer(
    name="ingest",
    help="Descarga incremental de fuentes publicas a la capa raw.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def principal() -> None:
    """Existe para que los comandos sigan siendo subcomandos.

    Con un solo comando registrado, typer colapsa el grupo y la invocacion
    pasaria a ser `ingest yellow`. Ya hay dos, asi que hoy no hace falta, pero
    quitarlo dejaria el contrato de la CLI a merced de cuantos comandos haya
    registrados en un momento dado.
    """


_MENSAJE = {
    Resultado.DESCARGADO: "descargado",
    Resultado.YA_PRESENTE: "ya presente, no se descargo nada",
    Resultado.REVISION: "REVISION del origen, se volvio a descargar",
    Resultado.NO_DISPONIBLE: "no publicado en el origen",
}


def _tamano(bytes_: int) -> str:
    """Escala la unidad al archivo.

    El rango real va de 12 KB del catalogo de zonas a 448 MB de un mes de 2009.
    Reportar todo en MB deja el catalogo en un inutil "0.0 MB".
    """
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1048576:
        return f"{bytes_ / 1024:.1f} KB"
    return f"{bytes_ / 1048576:.1f} MB"


def _reportar(informe: Informe) -> None:
    detalle = f"  {_tamano(informe.bytes)}" if informe.bytes else ""
    typer.echo(f"{informe.key}  {_MENSAJE[informe.resultado]}{detalle}")


def _morir(prefijo: str, err: Exception, codigo: int) -> typer.Exit:
    typer.secho(f"{prefijo}: {err}", fg=typer.colors.RED, err=True)
    return typer.Exit(codigo)


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
        raise _morir("configuracion", err, 3) from err

    try:
        informe = tlc.ingerir(almacen, origen, servicio, mes, forzar=forzar)
    except (tlc.MesInvalido, tlc.ServicioInvalido) as err:
        raise _morir("argumento", err, 2) from err
    except ErrorOrigen as err:
        raise _morir("origen", err, 1) from err
    except ErrorAlmacenamiento as err:
        raise _morir("destino", err, 1) from err

    _reportar(informe)

    # Un mes no publicado no es un fallo: en un backfill es la senal de que se
    # llego al final, y salir con error haria reintentar para siempre.


@app.command("tlc-zonas")
def comando_tlc_zonas(
    forzar: Annotated[bool, typer.Option("--forzar", help="Descarga aunque ya este")] = False,
) -> None:
    """Ingiere el catalogo de zonas de TLC a la capa raw.

    Comando hermano de `tlc` y no `tlc zonas`: ese grupo lleva el servicio como
    argumento posicional y el catalogo no es un servicio, asi que colgarlo ahi
    obligaria a inventar un valor centinela dentro de `SERVICIOS`.
    """
    try:
        almacen = almacen_raw()
        origen = OrigenZonasTLC.desde_entorno()
    except ErrorConfiguracion as err:
        raise _morir("configuracion", err, 3) from err

    try:
        informe = zonas.ingerir(almacen, origen, forzar=forzar)
    except ErrorOrigen as err:
        # A diferencia de `tlc`, aqui no hay respuesta de error que sea final
        # feliz: el catalogo siempre esta publicado.
        raise _morir("origen", err, 1) from err
    except ErrorAlmacenamiento as err:
        raise _morir("destino", err, 1) from err

    _reportar(informe)
