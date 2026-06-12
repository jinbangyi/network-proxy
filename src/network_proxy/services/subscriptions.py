import base64
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.db.models import Node
from network_proxy.settings import Settings


class SubscriptionService:
    def __init__(self, settings: Settings, session: Session | None = None):
        self.settings = settings
        self.session = session

    def get_raw_links(self) -> list[str]:
        database_links = self.get_database_links()
        if database_links:
            return database_links
        return self.settings.get_bootstrap_links()

    def get_database_links(self) -> list[str]:
        if self.session is None:
            return []
        statement = select(Node).where(
            Node.approval_status == "approved",
            Node.lifecycle_status != "disabled",
            Node.applied_config_version >= Node.desired_config_version,
        )
        nodes = list(self.session.scalars(statement))
        links: list[str] = []
        for node in nodes:
            link = self._build_node_link(node)
            if link:
                links.append(link)
        return links

    def _build_node_link(self, node: Node) -> str | None:
        if node.protocol != "vmess":
            return None
        credentials = json.loads(node.credential_json or "{}")
        host = node.public_host
        port = node.active_port
        if (
            node.published_mode == "relay"
            and node.relay_public_host
            and node.relay_public_port
        ):
            host = node.relay_public_host
            port = node.relay_public_port
        if not host or port is None or not credentials.get("client_id"):
            return None
        payload = {
            "v": "2",
            "ps": node.node_name,
            "add": host,
            "port": str(port),
            "id": credentials["client_id"],
            "aid": "0",
            "scy": credentials.get("security", "auto"),
            "net": credentials.get("network", "tcp"),
            "type": "none",
            "host": "",
            "path": "",
            "tls": "tls" if credentials.get("tls") else "",
        }
        encoded = base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("utf-8")
        return f"vmess://{encoded}"

    def get_raw_subscription(self) -> str:
        return "\n".join(self.get_raw_links())

    def get_encoded_subscription(self) -> str:
        raw_subscription = self.get_raw_subscription().encode("utf-8")
        return base64.b64encode(raw_subscription).decode("utf-8")

    async def get_clash_subscription(self, subscribe_url: str) -> str:
        if not self.settings.subconverter_url:
            raise RuntimeError("NETWORK_PROXY_SUBCONVERTER_URL is not configured")

        endpoint = f"{self.settings.subconverter_url.rstrip('/')}/sub"
        params = {
            "target": "clash",
            "url": subscribe_url,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
        return response.text
