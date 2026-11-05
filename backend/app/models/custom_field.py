"""Definições de campos customizados por tenant (schema adaptativo sem DDL).

Abordagem: registry + JSONB. Cada tenant define campos extras (ex.: "polo_de_apoio",
"turno_preferido") em `custom_field_definitions`; os valores ficam em
`students.custom_fields` (JSONB indexado por GIN), sem ALTER TABLE em runtime.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


CUSTOM_FIELD_TYPES = ("text", "integer", "number", "boolean", "date", "enum")


class CustomFieldDefinition(Base):
    __tablename__ = "custom_field_definitions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Alvo do campo. MVP: apenas "student"; o enum deixa porta para
    # "enrollment"/"financial" sem mudança estrutural.
    target: Mapped[str] = mapped_column(String(50), default="student", nullable=False)
    # Nome canônico em slug (ex.: "polo_de_apoio"). Imutável após criação.
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)  # CUSTOM_FIELD_TYPES
    # Opções permitidas quando data_type == "enum".
    options: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # LGPD: campo contém dado pessoal identificável → herda minimização/TTL.
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Aliases extras para o fuzzy matching de importação (ex.: ["polo", "polo de apoio presencial"]).
    aliases: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "target", "name", name="uq_custom_fields_tenant_target_name"),
        Index("ix_custom_fields_tenant_target", "tenant_id", "target", "active"),
    )
