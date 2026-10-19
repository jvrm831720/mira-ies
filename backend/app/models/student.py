"""
Modelos de domínio para persistência no Supabase (PostgreSQL).

Foco no MVP: UploadBatch + Student com features básicas de risco.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Text,
    ForeignKey,
    Index,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UploadBatch(Base):
    """Registro de cada upload de planilha realizado pela IES."""

    __tablename__ = "upload_batches"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="received", nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    columns: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    students: Mapped[list["Student"]] = relationship(
        "Student", back_populates="batch", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<UploadBatch {self.id} status={self.status} rows={self.total_rows}>"


class Student(Base):
    """Registro de aluno com features usadas no cálculo de risco."""

    __tablename__ = "students"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    batch_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("upload_batches.id", ondelete="CASCADE"), nullable=False
    )

    matricula: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    curso: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    turma: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    semestre: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forma_ingresso: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    dias_atraso_boleto: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorrencia_atrasos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dias_sem_login: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    presenca_percentual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nota_media: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reprovacoes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    shap_top_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    batch: Mapped["UploadBatch"] = relationship("UploadBatch", back_populates="students")

    __table_args__ = (
        Index("ix_students_batch_matricula", "batch_id", "matricula"),
        Index("ix_students_risk_level", "risk_level"),
        Index("ix_students_curso", "curso"),
    )

    def __repr__(self) -> str:
        return f"<Student {self.matricula} - {self.nome} risk={self.risk_score}>"
