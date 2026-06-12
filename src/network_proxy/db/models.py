import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class JoinRequest(Base, TimestampMixin):
    __tablename__ = "join_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    public_host: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_protocols: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    requested_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_modes: Mapped[str] = mapped_column(
        Text, default='["direct"]', nullable=False
    )
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True, nullable=False
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    join_request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("join_requests.id"),
        unique=True,
        nullable=False,
    )
    node_name: Mapped[str] = mapped_column(String(255), nullable=False)
    public_host: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protocol: Mapped[str] = mapped_column(String(64), nullable=False)
    active_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_assigned_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credential_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(32), default="approved", index=True, nullable=False
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default="provisioning", index=True, nullable=False
    )
    health_status: Mapped[str] = mapped_column(
        String(32), default="unknown", index=True, nullable=False
    )
    published_mode: Mapped[str] = mapped_column(
        String(32), default="direct", index=True, nullable=False
    )
    direct_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    relay_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    relay_public_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_public_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_config_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    applied_config_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retry_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_report_at: Mapped[datetime | None] = mapped_column(
        DateTime, index=True, nullable=True
    )


class HealthEvent(Base):
    __tablename__ = "health_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("nodes.id"), index=True, nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    probe_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    probe_result: Mapped[str] = mapped_column(String(32), nullable=False)
    old_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )


class AdminToken(Base):
    __tablename__ = "admin_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )


class SubscriptionToken(Base):
    __tablename__ = "subscription_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
