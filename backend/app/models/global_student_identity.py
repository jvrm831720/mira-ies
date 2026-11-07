"""Global portal identity is never a tenant student record.

Only a dedicated identity service may access these tables. No automatic links
to tenant Students or liabilities are created during registration.
"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def now_utc():
    return datetime.now(timezone.utc)


class GlobalStudentAccount(Base):
    __tablename__ = "mira_global_student_accounts"
    __table_args__ = (
        CheckConstraint("identity_verified_at IS NULL OR email_verified_at IS NOT NULL",
                        name="ck_global_identity_requires_email"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    cpf_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    identity_verification_method: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class GlobalStudentChallenge(Base):
    __tablename__ = "mira_global_student_challenges"
    __table_args__ = (
        CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_global_student_challenge_attempts"),
        CheckConstraint("purpose IN ('register','login')", name="ck_global_student_challenge_purpose"),
        Index("ix_global_student_challenge_account", "account_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class GlobalStudentSession(Base):
    __tablename__ = "mira_global_student_sessions"
    __table_args__ = (Index("ix_global_student_sessions_account", "account_id", "expires_at"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class GlobalStudentAttestation(Base):
    __tablename__ = "mira_global_student_attestations"
    nonce_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("mira_global_student_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
