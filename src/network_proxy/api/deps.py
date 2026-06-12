import hashlib
import json
from datetime import datetime

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.db.models import AdminToken, Node, SubscriptionToken
from network_proxy.db.session import get_db_session
from network_proxy.settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dependency() -> Settings:
    return get_settings()


def get_db(session: Session = Depends(get_db_session)) -> Session:
    return session


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings_dependency),
    session: Session = Depends(get_db),
) -> None:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing admin token",
        )
    if settings.admin_token and credentials.credentials == settings.admin_token:
        return
    token_hash = hash_token(credentials.credentials)
    statement = select(AdminToken).where(
        AdminToken.token_hash == token_hash,
        AdminToken.enabled.is_(True),
    )
    admin_token = session.scalars(statement).first()
    if admin_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
        )


def require_node(
    node_id: str,
    credentials: HTTPAuthorizationCredentials | None,
    session: Session,
) -> Node:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing node token",
        )
    node = session.get(Node, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="node not found"
        )
    credential_data = json.loads(node.credential_json or "{}")
    if credential_data.get("node_token_hash") != hash_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid node token",
        )
    return node


def require_subscription_access(
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings_dependency),
    session: Session = Depends(get_db),
) -> None:
    if settings.subscription_token:
        if token == settings.subscription_token:
            return

    now = datetime.utcnow()
    statement = select(SubscriptionToken).where(SubscriptionToken.enabled.is_(True))
    active_tokens = list(session.scalars(statement))
    active_tokens = [
        item
        for item in active_tokens
        if item.expires_at is None or item.expires_at > now
    ]
    if not active_tokens and not settings.subscription_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="subscription access is not configured",
        )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing subscription token",
        )
    token_hash = hash_token(token)
    for active_token in active_tokens:
        if active_token.token_hash == token_hash:
            return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid subscription token",
    )
