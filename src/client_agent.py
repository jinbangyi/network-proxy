import json
import time

import click

from network_proxy.client_agent import ClientAgent
from network_proxy.settings import get_settings


@click.command()
@click.option("--once", is_flag=True, help="Run a single reconciliation step and exit.")
@click.option("--interval", default=10, show_default=True, type=int)
def main(once: bool, interval: int) -> None:
    settings = get_settings()
    agent = ClientAgent(settings)
    if once:
        click.echo(json.dumps(agent.reconcile_once(), indent=2, sort_keys=True))
        return

    while True:
        state = agent.reconcile_once()
        click.echo(json.dumps(state, sort_keys=True))
        time.sleep(interval)


if __name__ == "__main__":
    main()
