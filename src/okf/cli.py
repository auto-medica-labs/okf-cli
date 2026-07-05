"""okf bundle — Plain markdown to OKF bundle converter."""

import typer

from okf.commands.bundle import bundle
from okf.commands.list import cmd_list
from okf.commands.show import cmd_show
from okf.commands.validate import validate

app = typer.Typer(
    name="okf",
    help="Open Knowledge Format tooling",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Convert plain markdown into OKF-conformant knowledge bundles."""
    pass


app.command()(bundle)
app.command("list")(cmd_list)
app.command("show")(cmd_show)
app.command("validate")(validate)


if __name__ == "__main__":
    app()
