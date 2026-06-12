import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
JINJA_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)


def render_v2ray_config(desired_state: dict[str, Any]) -> dict[str, Any]:
    publish_mode = desired_state.get("publish_mode") or "direct"
    if publish_mode == "relay":
        return build_relay_vmess_config(desired_state)
    return build_direct_vmess_config(desired_state)


def build_direct_vmess_config(desired_state: dict[str, Any]) -> dict[str, Any]:
    return _render_template("node-direct.json.j2", _build_direct_context(desired_state))


def build_relay_vmess_config(desired_state: dict[str, Any]) -> dict[str, Any]:
    relay_config = desired_state.get("relay_config", {})
    if not relay_config.get("host") or relay_config.get("port") is None:
        raise RuntimeError("relay publish mode requires relay host and port")
    return _render_template("node-relay.json.j2", _build_relay_context(desired_state))


def _render_template(template_name: str, context: dict[str, Any]) -> dict[str, Any]:
    rendered = JINJA_ENV.get_template(template_name).render(**context)
    return json.loads(rendered)


def _build_direct_context(desired_state: dict[str, Any]) -> dict[str, Any]:
    direct_config = desired_state.get("direct_config", {})
    credentials = desired_state.get("credentials", {})
    return {
        "listen_host": direct_config.get("host") or "0.0.0.0",
        "listen_port": direct_config.get("port") or 0,
        "client_id": credentials.get("client_id") or "",
        "security": credentials.get("security", "auto"),
        "network": credentials.get("network", "tcp"),
        "transport_security": "tls" if credentials.get("tls") else "none",
        "node_id": desired_state.get("node_id") or "node",
    }


def _build_relay_context(desired_state: dict[str, Any]) -> dict[str, Any]:
    direct_context = _build_direct_context(desired_state)
    relay_config = desired_state.get("relay_config", {})
    direct_context.update(
        {
            "relay_host": relay_config.get("host"),
            "relay_port": relay_config.get("port"),
            "relay_tag": f"relay-{desired_state.get('node_id') or 'node'}",
        }
    )
    return direct_context
