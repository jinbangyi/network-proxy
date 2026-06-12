import click
import uvicorn

from network_proxy.app import create_app
from network_proxy.settings import get_settings

app = create_app()


@click.command()
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
def start(host: str | None, port: int | None):
    settings = get_settings()
    uvicorn.run(
        app,
        host=host or settings.host,
        port=port or settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    start()
