from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from network_proxy.api.deps import bearer_scheme, get_db, require_node
from network_proxy.db.models import JoinRequest, Node
from network_proxy.services.onboarding import OnboardingService
from network_proxy.settings import Settings, get_settings

router = APIRouter(tags=["node"])


class JoinRequestCreate(BaseModel):
    node_name: str
    public_host: str
    region: str | None = None
    requested_protocols: list[str] = Field(default_factory=list)
    requested_port: int | None = None
    requested_modes: list[str] = Field(default_factory=lambda: ["direct"])
    agent_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JoinRequestStatusResponse(BaseModel):
    join_request_id: str
    status: str
    poll_after_seconds: int
    review_note: str | None = None
    node_id: str | None = None
    node_token: str | None = None


class DesiredStateResponse(BaseModel):
    node_id: str
    desired_config_version: int
    protocol: str
    publish_mode: str
    direct_config: dict[str, Any]
    relay_config: dict[str, Any]
    health_policy: dict[str, Any]
    credentials: dict[str, Any]


class HeartbeatRequest(BaseModel):
    agent_version: str | None = None
    v2ray_version: str | None = None
    local_status: str | None = None
    supports_relay: bool = False
    supports_restart: bool = True
    observed_errors: list[str] = Field(default_factory=list)


class NodeReportRequest(BaseModel):
    applied_config_version: int | None = None
    direct_effective_host: str | None = None
    direct_effective_port: int | None = None
    relay_effective_host: str | None = None
    relay_effective_port: int | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


def get_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> OnboardingService:
    return OnboardingService(session, settings)


@router.post(
    "/join-requests",
    response_model=JoinRequestStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_join_request(
    payload: JoinRequestCreate,
    service: OnboardingService = Depends(get_service),
    settings: Settings = Depends(get_settings),
) -> JoinRequestStatusResponse:
    join_request = service.create_join_request(**payload.model_dump())
    return JoinRequestStatusResponse(
        join_request_id=join_request.id,
        status=join_request.status,
        poll_after_seconds=settings.join_request_poll_after_seconds,
    )


@router.get(
    "/join-requests/{join_request_id}", response_model=JoinRequestStatusResponse
)
def get_join_request_status(
    join_request_id: str,
    service: OnboardingService = Depends(get_service),
    settings: Settings = Depends(get_settings),
) -> JoinRequestStatusResponse:
    join_request = service.get_join_request(join_request_id)
    if join_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="join request not found"
        )
    node = service.get_node_by_join_request(join_request_id)
    node_token = None
    if join_request.status == "approved" and node is not None:
        node_token = service.get_join_request_metadata(join_request).get("node_token")
    return JoinRequestStatusResponse(
        join_request_id=join_request.id,
        status=join_request.status,
        poll_after_seconds=settings.join_request_poll_after_seconds,
        review_note=join_request.review_note,
        node_id=node.id if node else None,
        node_token=node_token,
    )


def _get_authorized_node(
    node_id: str,
    session: Session = Depends(get_db),
    credentials=Depends(bearer_scheme),
) -> Node:
    return require_node(node_id, credentials, session)


@router.get("/nodes/{node_id}/desired-state", response_model=DesiredStateResponse)
def get_desired_state(
    node: Node = Depends(_get_authorized_node),
    service: OnboardingService = Depends(get_service),
) -> DesiredStateResponse:
    return DesiredStateResponse(**service.build_desired_state(node))


@router.post("/nodes/{node_id}/heartbeat")
def post_heartbeat(
    payload: HeartbeatRequest,
    node: Node = Depends(_get_authorized_node),
    service: OnboardingService = Depends(get_service),
) -> dict[str, str]:
    service.record_heartbeat(node, payload.model_dump())
    return {"status": "ok"}


@router.post("/nodes/{node_id}/report")
def post_report(
    payload: NodeReportRequest,
    node: Node = Depends(_get_authorized_node),
    service: OnboardingService = Depends(get_service),
) -> dict[str, str]:
    service.record_report(node, payload.model_dump())
    return {"status": "ok"}
