"""Modelos de dominio para persistencia no Supabase (PostgreSQL)."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, Index, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="received", nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="batch", cascade="all, delete-orphan"
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("upload_batches.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    matricula: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    curso: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    campus: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    status_aluno: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    turma: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    semestre: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forma_ingresso: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telefone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    communication_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    communication_opted_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Shape: {"channels": {"whatsapp": bool, "email": bool, "sms": bool},
    #         "topics": {"academic": bool, "retention": bool, "promotional": bool}}
    communication_preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    dias_atraso_boleto: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorrencia_atrasos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    saldo_devedor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status_financeiro: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    dias_sem_login: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    presenca_percentual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nota_media: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reprovacoes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    shap_top_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Base model score is stored separately from the transparent interaction-based adjustment.
    model_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dynamic_risk_adjustment: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    engagement_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    engagement_score_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Explicit allowlisted learning/behavior properties plus opt-in message field keys.
    behavior_properties: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    batch: Mapped["UploadBatch"] = relationship("UploadBatch", back_populates="students")

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_students_tenant_id_id"),
        Index("ix_students_batch_matricula", "batch_id", "matricula"),
        Index("ix_students_risk_level", "risk_level"),
        Index("ix_students_curso", "curso"),
    )
