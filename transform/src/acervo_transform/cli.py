"""Entrada de usuario."""

from typing import Annotated

import typer

from acervo_transform import contrato, silver
from acervo_transform.config import SparkConfig

app = typer.Typer(
    name="silver",
    help="Materializa la capa silver del lakehouse.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def principal() -> None:
    """Existe para que `tlc` siga siendo subcomando.

    Con un solo comando registrado, typer colapsa el grupo y la invocacion
    pasaria a ser `silver yellow`. Le paso a `ingest` y el contrato de la CLI no
    debe cambiar por cuantos comandos haya hoy.
    """


@app.command("tlc")
def comando_tlc(
    servicio: Annotated[
        str, typer.Argument(help=f"Uno de: {', '.join(sorted(contrato.CONTRATOS))}")
    ],
    mes: Annotated[str, typer.Option("--mes", help="Mes en formato YYYY-MM")],
) -> None:
    """Materializa un mes de TLC como particion de la tabla silver."""
    cfg = SparkConfig.desde_entorno()

    # Lo barato y local primero: que el mes y el servicio sean validos no
    # necesita una sesion de Spark, y abrirla para descubrir un typo es caro.
    try:
        silver.validar_mes(mes)
        contrato.contrato(servicio)
    except (silver.MesInvalido, contrato.ServicioSinContrato) as err:
        typer.secho(str(err), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from err

    sesion = silver.sesion(cfg)
    try:
        informe = silver.materializar(sesion, cfg, servicio, mes)
    except silver.MesNoEstaEnRaw as err:
        typer.secho(f"origen: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from err
    except contrato.EsquemaInvalido as err:
        typer.secho(f"esquema: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from err
    finally:
        sesion.stop()

    if informe.tabla_creada:
        typer.echo(f"{informe.tabla}  creada, particionada por mes")
    if informe.sobrantes:
        typer.secho(
            f"aviso: {len(informe.sobrantes)} columnas del origen fuera del contrato, "
            f"ignoradas: {', '.join(informe.sobrantes)}",
            fg=typer.colors.YELLOW,
        )

    pct = 100.0 * informe.marcadas / informe.leidas if informe.leidas else 0.0
    typer.echo(
        f"{informe.tabla}  mes={informe.mes}  "
        f"leidas={informe.leidas:,}  marcadas={informe.marcadas:,} ({pct:.2f}%)  "
        f"escritas={informe.escritas:,}"
    )

    # La postcondicion de CU-002. Que el comando termine no basta: si la
    # particion no tiene tantas filas que el origen, algo se perdio por el
    # camino y callarlo lo convierte en un dato malo que nadie mira.
    if not informe.coherente:
        typer.secho(
            f"FALLO  la particion tiene {informe.escritas:,} filas y el origen {informe.leidas:,}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
