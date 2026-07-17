"""okf-server CLI entrypoint."""

from __future__ import annotations

import typer

from okf.server.app import OKF_SERVER_VERSION, create_app
from okf.server.auth import UserStore
from okf.server.storage import FileStore

app = typer.Typer(name="okf-server")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8080),
    store: str = typer.Option("~/.okf/store"),
    database: str = typer.Option("~/.okf/server.db"),
    allow_register: bool = typer.Option(True, help="Allow new user registration"),
) -> None:
    """Run the okf-server HTTP API."""
    import uvicorn

    file_store = FileStore(store)
    user_store = UserStore(database)
    api = create_app(file_store, user_store, allow_register=allow_register)
    uvicorn.run(api, host=host, port=port)


@app.command()
def version() -> None:
    """Show the server version."""
    typer.echo(OKF_SERVER_VERSION)


if __name__ == "__main__":
    app()
