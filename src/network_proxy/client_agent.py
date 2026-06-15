import base64
import json
from pathlib import Path
from typing import Any

import httpx

from network_proxy.settings import Settings


class ClientAgent:
    """Polls the manager subscription endpoint and renders a V2Ray client config."""

    def __init__(self, settings: Settings, api_client: Any | None = None):
        self.settings = settings
        self.api_client = api_client

    def _request(self, path: str, **kwargs: Any) -> Any:
        if self.api_client is not None:
            response = self.api_client.get(path, **kwargs)
            response.raise_for_status()
            return response
        with httpx.Client(
            base_url=self.settings.client_manager_url, timeout=30.0
        ) as client:
            response = client.get(path, **kwargs)
            response.raise_for_status()
            return response

    def fetch_links(self) -> list[dict[str, Any]]:
        try:
            response = self._request(
                "/subscribe/raw",
                params={"token": self.settings.client_subscription_token},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 503:
                return []
            raise
        parsed: list[dict[str, Any]] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line.startswith("vmess://"):
                continue
            encoded = line[len("vmess://"):]
            try:
                decoded = base64.b64decode(encoded).decode("utf-8")
                parsed.append(json.loads(decoded))
            except (ValueError, json.JSONDecodeError):
                continue
        return parsed

    def select_link(self, links: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not links:
            return None
        wanted = self.settings.client_node_name
        if wanted:
            for link in links:
                if link.get("ps") == wanted:
                    return link
        return links[0]

    def build_client_config(self, link: dict[str, Any]) -> dict[str, Any]:
        host = self.settings.client_override_host or link.get("add", "")
        if self.settings.client_override_port is not None:
            port = self.settings.client_override_port
        else:
            port = int(link.get("port", 0))
        user_id = link.get("id", "")
        alter_id = int(link.get("aid", 0))
        security = link.get("scy", "auto")
        network = link.get("net", "tcp")
        use_tls = bool(link.get("tls"))
        stream_security = "tls" if use_tls else "none"

        inbounds: list[dict[str, Any]] = [
            {
                "listen": "0.0.0.0",
                "port": self.settings.client_socks_port,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            }
        ]
        if self.settings.client_http_port > 0:
            inbounds.append(
                {
                    "listen": "0.0.0.0",
                    "port": self.settings.client_http_port,
                    "protocol": "http",
                    "tag": "http-in",
                }
            )

        return {
            "log": {"loglevel": "warning"},
            "inbounds": inbounds,
            "outbounds": [
                {
                    "protocol": "vmess",
                    "settings": {
                        "vnext": [
                            {
                                "address": host,
                                "port": port,
                                "users": [
                                    {
                                        "id": user_id,
                                        "alterId": alter_id,
                                        "security": security,
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": network,
                        "security": stream_security,
                    },
                    "tag": "vmess-out",
                }
            ],
        }

    def load_state(self) -> dict[str, Any]:
        path = Path(self.settings.client_state_file)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_state(self, state: dict[str, Any]) -> None:
        path = Path(self.settings.client_state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
        )

    def config_signature(self, config: dict[str, Any]) -> str:
        return json.dumps(config, sort_keys=True)

    def apply_config(self, config: dict[str, Any]) -> dict[str, Any]:
        config_path = Path(self.settings.client_runtime_config_file)
        marker_path = Path(self.settings.client_reload_marker_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True), encoding="utf-8"
        )
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
        return {
            "config_path": str(config_path),
            "reload_marker": str(marker_path),
        }

    def reconcile_once(self) -> dict[str, Any]:
        state = self.load_state()
        links = self.fetch_links()
        state["links_seen"] = len(links)

        link = self.select_link(links)
        if link is None:
            state["status"] = "no_subscription"
            self.save_state(state)
            return state

        config = self.build_client_config(link)
        signature = self.config_signature(config)

        state["status"] = "active"
        state["selected"] = {
            "name": link.get("ps"),
            "host": config["outbounds"][0]["settings"]["vnext"][0]["address"],
            "port": config["outbounds"][0]["settings"]["vnext"][0]["port"],
        }

        if state.get("config_signature") != signature:
            apply_result = self.apply_config(config)
            state["config_signature"] = signature
            state["apply_result"] = apply_result

        self.save_state(state)
        return state
