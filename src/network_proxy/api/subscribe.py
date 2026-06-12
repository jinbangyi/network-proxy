from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from network_proxy.api.deps import get_db, require_subscription_access
from network_proxy.services.subscriptions import SubscriptionService
from network_proxy.settings import get_settings

router = APIRouter()


def _build_subscribe_url(request: Request) -> str:
    settings = get_settings()
    if settings.manager_public_url:
        return f"{settings.manager_public_url.rstrip('/')}/subscribe"
    return str(request.url_for("subscribe"))


@router.get("/", response_class=PlainTextResponse, include_in_schema=False)
@router.get("/subscribe", response_class=PlainTextResponse)
async def subscribe(
    _: None = Depends(require_subscription_access),
    session: Session = Depends(get_db),
) -> str:
    service = SubscriptionService(get_settings(), session)
    return service.get_encoded_subscription()


@router.get("/subscribe/raw", response_class=PlainTextResponse)
async def subscribe_raw(
    _: None = Depends(require_subscription_access),
    session: Session = Depends(get_db),
) -> str:
    service = SubscriptionService(get_settings(), session)
    return service.get_raw_subscription()


@router.get("/subscribe/clash", response_class=PlainTextResponse)
async def subscribe_clash(
    request: Request,
    _: None = Depends(require_subscription_access),
    session: Session = Depends(get_db),
) -> str:
    service = SubscriptionService(get_settings(), session)
    try:
        return await service.get_clash_subscription(_build_subscribe_url(request))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
