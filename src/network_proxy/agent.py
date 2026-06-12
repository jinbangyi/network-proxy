import json
from pathlib import Path
from typing import Any

import httpx

from network_proxy.services.config_render import render_v2ray_config
from network_proxy.services.runtime_control import RuntimeControlService
from network_proxy.settings import Settings


class NodeAgent:
    def __init__(self, settings: Settings, api_client: Any | None = None):
        self.settings = settings
        self.api_client = api_client

    def load_state(self) -> dict[str, Any]:
        path = Path(self.settings.node_state_file)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_state(self, state: dict[str, Any]) -> None:
        path = Path(self.settings.node_state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def save_desired_state(self, desired_state: dict[str, Any]) -> None:
        path = Path(self.settings.node_desired_state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(desired_state, indent=2, sort_keys=True), encoding="utf-8"
        )

    def render_runtime_config(self, desired_state: dict[str, Any]) -> dict[str, Any]:
        protocol = desired_state.get("protocol")
        if protocol != "vmess":
            raise RuntimeError(f"unsupported protocol: {protocol}")
        return render_v2ray_config(desired_state)

    def apply_runtime_config(self, desired_state: dict[str, Any]) -> dict[str, Any]:
        config = self.render_runtime_config(desired_state)
        runtime = RuntimeControlService(
            config_path=self.settings.node_runtime_config_file,
            validate_command=self.settings.node_validate_command,
            apply_command=self.settings.node_apply_command,
        )
        config_path = runtime.write_config(config)
        validate_result = runtime.validate()
        apply_result = runtime.apply()
        return {
            "config_path": config_path,
            "validate_result": validate_result,
            "apply_result": apply_result,
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.api_client is not None:
            response = getattr(self.api_client, method.lower())(path, **kwargs)
            response.raise_for_status()
            return response
        with httpx.Client(
            base_url=self.settings.node_manager_url, timeout=30.0
        ) as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

    def submit_join_request(self) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/join-requests",
            json={
                "node_name": self.settings.node_name,
                "public_host": self.settings.node_public_host,
                "region": self.settings.node_region,
                "requested_protocols": self.settings.get_requested_protocols(),
                "requested_port": self.settings.node_requested_port,
                "requested_modes": self.settings.get_requested_modes(),
                "agent_version": self.settings.node_agent_version,
                "metadata": {},
            },
        )
        return response.json()

    def poll_join_request(self, join_request_id: str) -> dict[str, Any]:
        response = self._request("GET", f"/join-requests/{join_request_id}")
        return response.json()

    def fetch_desired_state(self, node_id: str, node_token: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/nodes/{node_id}/desired-state",
            headers={"Authorization": f"Bearer {node_token}"},
        )
        return response.json()

    def send_heartbeat(
        self, node_id: str, node_token: str, local_status: str = "healthy"
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/nodes/{node_id}/heartbeat",
            headers={"Authorization": f"Bearer {node_token}"},
            json={
                "agent_version": self.settings.node_agent_version,
                "local_status": local_status,
                "supports_relay": "relay" in self.settings.get_requested_modes(),
                "supports_restart": True,
                "observed_errors": [],
            },
        )
        return response.json()

    def send_report(
        self,
        node_id: str,
        node_token: str,
        desired_state: dict[str, Any],
        runtime_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        direct_config = desired_state.get("direct_config", {})
        relay_config = desired_state.get("relay_config", {})
        response = self._request(
            "POST",
            f"/nodes/{node_id}/report",
            headers={"Authorization": f"Bearer {node_token}"},
            json={
                "applied_config_version": desired_state.get("desired_config_version"),
                "direct_effective_host": direct_config.get("host"),
                "direct_effective_port": direct_config.get("port"),
                "relay_effective_host": relay_config.get("host"),
                "relay_effective_port": relay_config.get("port"),
                "runtime_metadata": runtime_metadata
                or {"mode": desired_state.get("publish_mode")},
            },
        )
        return response.json()

    def reconcile_once(self) -> dict[str, Any]:
        state = self.load_state()
        if not state.get("join_request_id"):
            join_request = self.submit_join_request()
            state["join_request_id"] = join_request["join_request_id"]
            state["status"] = join_request["status"]
            self.save_state(state)
            return state

        if not state.get("node_id") or not state.get("node_token"):
            join_status = self.poll_join_request(state["join_request_id"])
            state["status"] = join_status["status"]
            if join_status.get("node_id") and join_status.get("node_token"):
                state["node_id"] = join_status["node_id"]
                state["node_token"] = join_status["node_token"]
            self.save_state(state)
            return state

        desired_state = self.fetch_desired_state(state["node_id"], state["node_token"])
        self.save_desired_state(desired_state)
        runtime_state = self.apply_runtime_config(desired_state)
        self.send_heartbeat(state["node_id"], state["node_token"])
        self.send_report(
            state["node_id"],
            state["node_token"],
            desired_state,
            runtime_metadata=runtime_state,
        )
        state["status"] = "active"
        state["desired_config_version"] = desired_state.get("desired_config_version")
        state["runtime"] = runtime_state
        self.save_state(state)
        return state
