import sys
from pathlib import Path
import secrets

import click
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from network_proxy.app import create_app
from network_proxy.db.migrations import init_database
from network_proxy.db.session import SessionLocal
from network_proxy.settings import get_settings
from network_proxy.services.tokens import TokenService


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


@cli.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def serve(host: str | None, port: int | None) -> None:
    settings = get_settings()
    uvicorn.run(
        create_app(),
        host=host or settings.host,
        port=port or settings.port,
        log_level=settings.log_level,
    )


@cli.command("create-admin-token")
@click.option("--name", default="default-admin", show_default=True)
@click.option("--token", default=None)
def create_admin_token(name: str, token: str | None) -> None:
    init_database()
    raw_token = token or secrets.token_urlsafe(24)
    with SessionLocal() as session:
        token_service = TokenService(session)
        token_service.create_admin_token(name=name, raw_token=raw_token)
    click.echo(raw_token)


@cli.command("create-subscription-token")
@click.option("--name", default="default-subscription", show_default=True)
@click.option("--token", default=None)
@click.option("--description", default=None)
def create_subscription_token(
    name: str, token: str | None, description: str | None
) -> None:
    init_database()
    raw_token = token or secrets.token_urlsafe(24)
    with SessionLocal() as session:
        token_service = TokenService(session)
        token_service.create_subscription_token(
            name=name,
            raw_token=raw_token,
            description=description,
        )
    click.echo(raw_token)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
