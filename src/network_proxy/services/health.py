from datetime import datetime, timedelta
import socket

from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.db.models import HealthEvent, Node
from network_proxy.services.relay import RelayService
from network_proxy.settings import Settings


class HealthService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def run_once(self) -> dict[str, int]:
        statement = select(Node).where(
            Node.approval_status == "approved",
            Node.lifecycle_status != "disabled",
        )
        nodes = list(self.session.scalars(statement))
        checked_nodes = 0
        rotated_nodes = 0
        relay_switched_nodes = 0
        disabled_nodes = 0
        for node in nodes:
            checked_nodes += 1
            outcome = self.check_node(node)
            if outcome == "rotated":
                rotated_nodes += 1
            if outcome == "relay_switched":
                relay_switched_nodes += 1
            if outcome == "disabled":
                disabled_nodes += 1
        self.session.commit()
        RelayService(self.session, self.settings).sync_manager_runtime_config()
        return {
            "checked_nodes": checked_nodes,
            "rotated_nodes": rotated_nodes,
            "relay_switched_nodes": relay_switched_nodes,
            "disabled_nodes": disabled_nodes,
        }

    def check_node(self, node: Node) -> str:
        now = datetime.utcnow()
        node.last_check_at = now
        if node.applied_config_version < node.desired_config_version:
            self.session.add(node)
            return "awaiting_apply"

        if node.published_mode == "relay":
            return self._check_relay_node(node, now)

        if self._probe(node.public_host, node.active_port):
            return self._mark_healthy(
                node,
                now,
                probe_scope="direct",
                old_port=node.active_port,
                new_port=node.active_port,
                detail="direct probe succeeded",
            )

        node.health_status = "degraded"
        node.retry_count += 1
        old_port = node.active_port
        if node.retry_count <= node.max_retry_count and node.active_port is not None:
            node.active_port += self.settings.health_check_port_step
            node.last_assigned_port = node.active_port
            node.desired_config_version += 1
            self.session.add(
                HealthEvent(
                    node_id=node.id,
                    attempt_no=node.retry_count,
                    probe_scope="direct",
                    probe_result="failure",
                    old_port=old_port,
                    new_port=node.active_port,
                    action="rotate_port",
                    detail="direct probe failed; rotated desired port",
                )
            )
            self.session.add(node)
            return "rotated"

        if self._can_switch_to_relay(node):
            return self._switch_to_relay(node, old_port)

        return self._disable_node(
            node,
            probe_scope="direct",
            old_port=old_port,
            new_port=old_port,
            detail="direct probe failed after retry budget",
        )

    def _check_relay_node(self, node: Node, now: datetime) -> str:
        relay_host, relay_port = self._get_relay_endpoint(node)
        if self._probe(relay_host, relay_port):
            return self._mark_healthy(
                node,
                now,
                probe_scope="relay",
                old_port=relay_port,
                new_port=relay_port,
                detail="relay probe succeeded",
            )

        node.health_status = "degraded"
        return self._disable_node(
            node,
            probe_scope="relay",
            old_port=relay_port,
            new_port=relay_port,
            detail="relay probe failed after direct remediation",
        )

    def _mark_healthy(
        self,
        node: Node,
        now: datetime,
        *,
        probe_scope: str,
        old_port: int | None,
        new_port: int | None,
        detail: str,
    ) -> str:
        node.health_status = "healthy"
        node.retry_count = 0
        node.last_success_at = now
        node.lifecycle_status = "active"
        self.session.add(
            HealthEvent(
                node_id=node.id,
                attempt_no=0,
                probe_scope=probe_scope,
                probe_result="success",
                old_port=old_port,
                new_port=new_port,
                action="healthy",
                detail=detail,
            )
        )
        self.session.add(node)
        return "healthy"

    def _disable_node(
        self,
        node: Node,
        *,
        probe_scope: str,
        old_port: int | None,
        new_port: int | None,
        detail: str,
    ) -> str:
        node.lifecycle_status = "disabled"
        self.session.add(
            HealthEvent(
                node_id=node.id,
                attempt_no=node.retry_count,
                probe_scope=probe_scope,
                probe_result="failure",
                old_port=old_port,
                new_port=new_port,
                action="disable_node",
                detail=detail,
            )
        )
        self.session.add(node)
        return "disabled"

    def _can_switch_to_relay(self, node: Node) -> bool:
        if not node.relay_enabled:
            return False
        if not self._has_fresh_report(node):
            return False
        relay_host, relay_port = self._get_relay_endpoint(node)
        return bool(relay_host and relay_port is not None)

    def _switch_to_relay(self, node: Node, old_port: int | None) -> str:
        relay_host = node.relay_public_host or self.settings.get_manager_relay_host()
        relay_port = RelayService(self.session, self.settings).allocate_relay_port(node)
        if not relay_host or relay_port is None:
            return self._disable_node(
                node,
                probe_scope="relay",
                old_port=old_port,
                new_port=old_port,
                detail="direct probe failed after retry budget and no relay endpoint was available",
            )
        node.published_mode = "relay"
        node.relay_public_host = relay_host
        node.relay_public_port = relay_port
        node.desired_config_version += 1
        node.lifecycle_status = "provisioning"
        node.retry_count = 0
        self.session.add(
            HealthEvent(
                node_id=node.id,
                attempt_no=node.max_retry_count + 1,
                probe_scope="relay",
                probe_result="fallback",
                old_port=old_port,
                new_port=relay_port,
                action="switch_to_relay",
                detail="direct probe failed after retry budget; switching published mode to relay",
            )
        )
        self.session.add(node)
        return "relay_switched"

    def _has_fresh_report(self, node: Node) -> bool:
        if node.last_report_at is None:
            return False
        freshness_cutoff = datetime.utcnow() - timedelta(
            seconds=self.settings.node_stale_after_seconds
        )
        return node.last_report_at >= freshness_cutoff

    def _get_relay_endpoint(self, node: Node) -> tuple[str | None, int | None]:
        return (
            node.relay_public_host or self.settings.get_manager_relay_host(),
            node.relay_public_port or self.settings.manager_relay_public_port,
        )

    def _probe(self, host: str | None, port: int | None) -> bool:
        if not host or port is None:
            return False
        try:
            with socket.create_connection(
                (host, port), timeout=self.settings.health_check_timeout_seconds
            ):
                return True
        except OSError:
            return False
