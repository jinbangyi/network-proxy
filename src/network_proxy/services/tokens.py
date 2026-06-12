from sqlalchemy import select
from sqlalchemy.orm import Session

from network_proxy.api.deps import hash_token
from network_proxy.db.models import AdminToken, SubscriptionToken


class TokenService:
    def __init__(self, session: Session):
        self.session = session

    def create_admin_token(self, *, name: str, raw_token: str) -> AdminToken:
        token_hash = hash_token(raw_token)
        existing = self.session.scalars(
            select(AdminToken).where(AdminToken.token_hash == token_hash)
        ).first()
        if existing is not None:
            if not existing.enabled:
                existing.enabled = True
                self.session.add(existing)
                self.session.commit()
                self.session.refresh(existing)
            return existing
        admin_token = AdminToken(name=name, token_hash=token_hash, enabled=True)
        self.session.add(admin_token)
        self.session.commit()
        self.session.refresh(admin_token)
        return admin_token

    def create_subscription_token(
        self,
        *,
        name: str,
        raw_token: str,
        description: str | None = None,
    ) -> SubscriptionToken:
        token_hash = hash_token(raw_token)
        existing = self.session.scalars(
            select(SubscriptionToken).where(SubscriptionToken.token_hash == token_hash)
        ).first()
        if existing is not None:
            existing.enabled = True
            if description is not None:
                existing.description = description
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing
        subscription_token = SubscriptionToken(
            name=name,
            token_hash=token_hash,
            enabled=True,
            description=description,
        )
        self.session.add(subscription_token)
        self.session.commit()
        self.session.refresh(subscription_token)
        return subscription_token
