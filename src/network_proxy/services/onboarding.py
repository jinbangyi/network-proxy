import json
import secrets
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.api.deps import hash_token
from network_proxy.db.models import JoinRequest, Node
from network_proxy.services.relay import RelayService
from network_proxy.settings import Settings


class OnboardingService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def create_join_request(
        self,
        *,
        node_name: str,
        public_host: str,
        region: str | None,
        requested_protocols: list[str],
        requested_port: int | None,
        requested_modes: list[str],
        agent_version: str | None,
        metadata: dict,
    ) -> JoinRequest:
        join_request = JoinRequest(
            node_name=node_name,
            public_host=public_host,
            region=region,
            agent_version=agent_version,
            requested_protocols=json.dumps(
                requested_protocols or [self.settings.default_node_protocol]
            ),
            requested_port=requested_port,
            requested_modes=json.dumps(requested_modes or ["direct"]),
            metadata_json=json.dumps(metadata or {}),
        )
        self.session.add(join_request)
        self.session.commit()
        self.session.refresh(join_request)
        return join_request

    def list_join_requests(self) -> list[JoinRequest]:
        statement = select(JoinRequest).order_by(JoinRequest.created_at.desc())
        return list(self.session.scalars(statement))

    def get_join_request(self, join_request_id: str) -> JoinRequest | None:
        return self.session.get(JoinRequest, join_request_id)

    def get_join_request_metadata(self, join_request: JoinRequest) -> dict:
        return json.loads(join_request.metadata_json or "{}")

    def approve_join_request(
        self,
        join_request: JoinRequest,
        *,
        protocol: str | None,
        publish_mode: str | None,
        assigned_port: int | None,
        review_note: str | None,
    ) -> tuple[Node, str]:
        requested_protocols = json.loads(join_request.requested_protocols)
        requested_modes = json.loads(join_request.requested_modes)
        node_token = secrets.token_urlsafe(24)
        node = Node(
            join_request_id=join_request.id,
            node_name=join_request.node_name,
            public_host=join_request.public_host,
            region=join_request.region,
            protocol=protocol
            or requested_protocols[0]
            or self.settings.default_node_protocol,
            active_port=assigned_port or join_request.requested_port,
            last_assigned_port=assigned_port or join_request.requested_port,
            credential_json=json.dumps(
                {
                    "node_token_hash": hash_token(node_token),
                    "client_id": str(uuid.uuid4()),
                    "network": "tcp",
                    "security": "auto",
                    "tls": False,
                }
            ),
            approval_status="approved",
            lifecycle_status="provisioning",
            health_status="unknown",
            published_mode=publish_mode
            or (requested_modes[0] if requested_modes else "direct"),
            direct_enabled="direct" in requested_modes,
            relay_enabled="relay" in requested_modes,
            desired_config_version=1,
            applied_config_version=0,
            max_retry_count=self.settings.default_max_retry_count,
        )
        metadata = self.get_join_request_metadata(join_request)
        metadata["node_token"] = node_token
        join_request.status = "approved"
        join_request.review_note = review_note
        join_request.metadata_json = json.dumps(metadata)
        self.session.add(node)
        self.session.commit()
        self.session.refresh(join_request)
        self.session.refresh(node)
        RelayService(self.session, self.settings).sync_manager_runtime_config()
        return node, node_token

    def reject_join_request(
        self, join_request: JoinRequest, review_note: str | None
    ) -> JoinRequest:
        join_request.status = "rejected"
        join_request.review_note = review_note
        self.session.add(join_request)
        self.session.commit()
        self.session.refresh(join_request)
        return join_request

    def get_node_by_join_request(self, join_request_id: str) -> Node | None:
        statement = select(Node).where(Node.join_request_id == join_request_id)
        return self.session.scalars(statement).first()

    def list_nodes(self) -> list[Node]:
        statement = select(Node).order_by(Node.created_at.desc())
        return list(self.session.scalars(statement))

    def build_desired_state(self, node: Node) -> dict:
        credentials = json.loads(node.credential_json or "{}")
        return {
            "node_id": node.id,
            "desired_config_version": node.desired_config_version,
            "protocol": node.protocol,
            "publish_mode": node.published_mode,
            "direct_config": {
                "enabled": node.direct_enabled,
                "host": node.public_host,
                "port": node.active_port,
            },
            "relay_config": {
                "enabled": node.relay_enabled,
                "host": node.relay_public_host,
                "port": node.relay_public_port,
            },
            "health_policy": {
                "max_retry_count": node.max_retry_count,
            },
            "credentials": {
                "client_id": credentials.get("client_id"),
                "network": credentials.get("network", "tcp"),
                "security": credentials.get("security", "auto"),
                "tls": credentials.get("tls", False),
            },
        }

    def record_heartbeat(self, node: Node, payload: dict) -> Node:
        now = datetime.utcnow()
        node.last_report_at = now
        node.lifecycle_status = "active"
        if payload.get("local_status"):
            node.health_status = payload["local_status"]
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        RelayService(self.session, self.settings).sync_manager_runtime_config()
        return node

    def record_report(self, node: Node, payload: dict) -> Node:
        now = datetime.utcnow()
        node.last_report_at = now
        applied_version = payload.get("applied_config_version")
        if applied_version is not None:
            node.applied_config_version = applied_version
            if applied_version >= node.desired_config_version:
                node.lifecycle_status = "active"
        direct_effective_port = payload.get("direct_effective_port")
        if direct_effective_port is not None:
            node.active_port = direct_effective_port
        direct_effective_host = payload.get("direct_effective_host")
        if direct_effective_host:
            node.public_host = direct_effective_host
        relay_effective_host = payload.get("relay_effective_host")
        relay_effective_port = payload.get("relay_effective_port")
        if relay_effective_host:
            node.relay_public_host = relay_effective_host
        if relay_effective_port is not None:
            node.relay_public_port = relay_effective_port
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        RelayService(self.session, self.settings).sync_manager_runtime_config()
        return node
