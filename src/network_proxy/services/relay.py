import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.db.models import Node
from network_proxy.settings import Settings


class RelayService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def sync_manager_runtime_config(self) -> str:
        config = self.build_manager_runtime_config()
        path = Path(self.settings.manager_relay_config_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)

    def build_manager_runtime_config(self) -> dict:
        inbounds = []
        outbounds = [
            {
                "tag": "direct",
                "protocol": "freedom",
                "settings": {},
            }
        ]
        rules = []

        for node in self.list_active_relay_nodes():
            relay_entry = self._build_relay_entry(node)
            if relay_entry is None:
                continue
            inbounds.append(relay_entry["inbound"])
            outbounds.append(relay_entry["outbound"])
            rules.append(relay_entry["rule"])

        return {
            "log": {"loglevel": "warning"},
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": {"domainStrategy": "AsIs", "rules": rules},
        }

    def list_active_relay_nodes(self) -> list[Node]:
        statement = select(Node).where(
            Node.approval_status == "approved",
            Node.lifecycle_status != "disabled",
            Node.published_mode == "relay",
            Node.applied_config_version >= Node.desired_config_version,
        )
        return list(self.session.scalars(statement))

    def allocate_relay_port(self, node: Node) -> int | None:
        if node.relay_public_port is not None:
            return node.relay_public_port

        used_ports = {
            port
            for port in self.session.scalars(
                select(Node.relay_public_port).where(
                    Node.id != node.id,
                    Node.relay_public_port.is_not(None),
                    Node.lifecycle_status != "disabled",
                )
            )
            if port is not None
        }

        start = self.settings.manager_relay_public_port
        end = start + self.settings.manager_relay_port_pool_size
        for port in range(start, end):
            if port not in used_ports:
                return port
        return None

    def _build_relay_entry(self, node: Node) -> dict | None:
        relay_port = node.relay_public_port
        if relay_port is None or node.active_port is None:
            return None

        credentials = json.loads(node.credential_json or "{}")
        client_id = credentials.get("client_id")
        if not client_id or not node.public_host:
            return None

        inbound_tag = f"relay-in-{node.id}"
        outbound_tag = f"relay-out-{node.id}"
        security = credentials.get("security", "auto")
        network = credentials.get("network", "tcp")
        transport_security = "tls" if credentials.get("tls") else "none"

        return {
            "inbound": {
                "tag": inbound_tag,
                "listen": "0.0.0.0",
                "port": relay_port,
                "protocol": "vmess",
                "settings": {
                    "clients": [
                        {
                            "id": client_id,
                            "alterId": 0,
                            "security": security,
                            "email": node.id,
                        }
                    ]
                },
                "streamSettings": {
                    "network": network,
                    "security": transport_security,
                },
            },
            "outbound": {
                "tag": outbound_tag,
                "protocol": "vmess",
                "settings": {
                    "vnext": [
                        {
                            "address": node.public_host,
                            "port": node.active_port,
                            "users": [
                                {
                                    "id": client_id,
                                    "alterId": 0,
                                    "security": security,
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": network,
                    "security": transport_security,
                },
            },
            "rule": {
                "type": "field",
                "inboundTag": [inbound_tag],
                "outboundTag": outbound_tag,
            },
        }
