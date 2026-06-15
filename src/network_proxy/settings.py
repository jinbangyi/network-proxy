from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NETWORK_PROXY_",
        case_sensitive=False,
    )

    app_name: str = "Network Proxy Manager"
    app_version: str = "0.1.0"
    app_description: str = (
        "Manager bootstrap service for proxy subscription publication."
    )
    host: str = "0.0.0.0"
    port: int = 9001
    log_level: str = "info"
    database_url: str = "sqlite:///data/network_proxy.db"
    admin_token: str | None = None
    manager_public_url: str | None = None
    manager_relay_public_host: str | None = None
    manager_relay_public_port: int = 31001
    manager_relay_port_pool_size: int = 20
    manager_relay_config_file: str = "data/manager-v2ray-config.json"
    subconverter_url: str | None = None
    bootstrap_subscription_links: str = ""
    bootstrap_subscription_links_file: str | None = None
    default_node_protocol: str = "vmess"
    default_max_retry_count: int = 3
    join_request_poll_after_seconds: int = 10
    subscription_token: str | None = None
    node_manager_url: str = "http://127.0.0.1:9001"
    node_name: str = "node-1"
    node_public_host: str = "127.0.0.1"
    node_region: str | None = None
    node_requested_protocols: str = "vmess"
    node_requested_modes: str = "direct"
    node_requested_port: int | None = None
    node_agent_version: str = "0.1.0"
    node_state_file: str = "data/node-agent-state.json"
    node_desired_state_file: str = "data/node-desired-state.json"
    node_runtime_config_file: str = "data/node-v2ray-config.json"
    node_apply_command: str | None = None
    node_validate_command: str | None = None
    health_check_enabled: bool = False
    health_check_dry_run: bool = False
    health_check_interval_seconds: int = 60
    health_check_timeout_seconds: float = 2.0
    health_check_port_step: int = 1
    node_stale_after_seconds: int = 120

    client_manager_url: str = "http://127.0.0.1:9001"
    client_subscription_token: str = "sub-db"
    client_socks_port: int = 10808
    client_http_port: int = 10809
    client_override_host: str | None = None
    client_override_port: int | None = None
    client_node_name: str | None = None
    client_runtime_config_file: str = "data/client-v2ray-config.json"
    client_reload_marker_file: str = "data/client-v2ray-reload.marker"
    client_state_file: str = "data/client-agent-state.json"
    client_interval: int = 10

    def get_bootstrap_links(self) -> list[str]:
        raw_value = self.bootstrap_subscription_links
        if self.bootstrap_subscription_links_file:
            file_path = Path(self.bootstrap_subscription_links_file)
            if file_path.exists():
                raw_value = file_path.read_text(encoding="utf-8")

        parts: list[str] = []
        for line in raw_value.splitlines():
            for item in line.split(","):
                value = item.strip()
                if value:
                    parts.append(value)
        return parts

    def get_requested_protocols(self) -> list[str]:
        return [
            item.strip()
            for item in self.node_requested_protocols.split(",")
            if item.strip()
        ]

    def get_requested_modes(self) -> list[str]:
        return [
            item.strip()
            for item in self.node_requested_modes.split(",")
            if item.strip()
        ]

    def get_manager_relay_host(self) -> str | None:
        if self.manager_relay_public_host:
            return self.manager_relay_public_host
        if not self.manager_public_url:
            return None
        return urlparse(self.manager_public_url).hostname


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
