from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from network_proxy.api.deps import get_db, require_admin
from network_proxy.services.health import HealthService
from network_proxy.services.onboarding import OnboardingService
from network_proxy.api.node import get_service
from network_proxy.services.tokens import TokenService
from network_proxy.settings import Settings, get_settings

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


class JoinRequestSummary(BaseModel):
    id: str
    node_name: str
    public_host: str
    region: str | None
    status: str
    requested_port: int | None
    review_note: str | None


class ApproveJoinRequest(BaseModel):
    protocol: str | None = None
    publish_mode: str | None = None
    assigned_port: int | None = None
    review_note: str | None = None


class RejectJoinRequest(BaseModel):
    review_note: str | None = None


class NodeSummary(BaseModel):
    id: str
    join_request_id: str
    node_name: str
    public_host: str
    region: str | None
    protocol: str
    active_port: int | None
    desired_config_version: int
    applied_config_version: int
    lifecycle_status: str
    health_status: str
    published_mode: str


class CreateSubscriptionTokenRequest(BaseModel):
    name: str
    token: str
    description: str | None = None


class RunHealthCheckResponse(BaseModel):
    checked_nodes: int
    rotated_nodes: int
    relay_switched_nodes: int
    disabled_nodes: int


@router.get("/join-requests", response_model=list[JoinRequestSummary])
def list_join_requests(
    service: OnboardingService = Depends(get_service),
) -> list[JoinRequestSummary]:
    return [
        JoinRequestSummary(
            id=item.id,
            node_name=item.node_name,
            public_host=item.public_host,
            region=item.region,
            status=item.status,
            requested_port=item.requested_port,
            review_note=item.review_note,
        )
        for item in service.list_join_requests()
    ]


@router.post("/join-requests/{join_request_id}/approve")
def approve_join_request(
    join_request_id: str,
    payload: ApproveJoinRequest,
    service: OnboardingService = Depends(get_service),
) -> dict[str, Any]:
    join_request = service.get_join_request(join_request_id)
    if join_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="join request not found"
        )
    if join_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="join request is not pending"
        )
    node, node_token = service.approve_join_request(
        join_request, **payload.model_dump()
    )
    return {
        "join_request_id": join_request.id,
        "node_id": node.id,
        "node_token": node_token,
        "desired_config_version": node.desired_config_version,
    }


@router.post("/join-requests/{join_request_id}/reject")
def reject_join_request(
    join_request_id: str,
    payload: RejectJoinRequest,
    service: OnboardingService = Depends(get_service),
) -> dict[str, str]:
    join_request = service.get_join_request(join_request_id)
    if join_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="join request not found"
        )
    if join_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="join request is not pending"
        )
    service.reject_join_request(join_request, payload.review_note)
    return {"status": "rejected"}


@router.get("/nodes", response_model=list[NodeSummary])
def list_nodes(service: OnboardingService = Depends(get_service)) -> list[NodeSummary]:
    return [
        NodeSummary(
            id=node.id,
            join_request_id=node.join_request_id,
            node_name=node.node_name,
            public_host=node.public_host,
            region=node.region,
            protocol=node.protocol,
            active_port=node.active_port,
            desired_config_version=node.desired_config_version,
            applied_config_version=node.applied_config_version,
            lifecycle_status=node.lifecycle_status,
            health_status=node.health_status,
            published_mode=node.published_mode,
        )
        for node in service.list_nodes()
    ]


@router.post("/subscription-tokens")
def create_subscription_token(
    payload: CreateSubscriptionTokenRequest,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    token_service = TokenService(session)
    token_service.create_subscription_token(
        name=payload.name,
        raw_token=payload.token,
        description=payload.description,
    )
    return {"status": "created"}


@router.post("/health/run", response_model=RunHealthCheckResponse)
def run_health_check(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RunHealthCheckResponse:
    health_service = HealthService(session, settings)
    result = health_service.run_once()
    return RunHealthCheckResponse(**result)
