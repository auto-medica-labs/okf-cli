"""okf — Open Knowledge Format tooling."""

from importlib.metadata import version as _version

import typer

from okf.commands.bundle import bundle
from okf.commands.list import cmd_list
from okf.commands.read import cmd_read
from okf.commands.validate import validate
from okf.core import console

app = typer.Typer(
    name="okf",
    help="Open Knowledge Format tooling",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"okf {_version('okf-cli')}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Convert plain markdown into OKF-conformant knowledge bundles."""


app.command()(bundle)
app.command("list")(cmd_list)
app.command("read")(cmd_read)
app.command("validate")(validate)


if __name__ == "__main__":
    app()
