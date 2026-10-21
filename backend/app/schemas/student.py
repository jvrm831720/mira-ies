from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class UploadBatchCreate(BaseModel):
    filename: str
    original_filename: str
    total_rows: int = 0
    columns: Optional[list[str]] = None


class UploadBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_filename: str
    status: str
    total_rows: int
    processed_rows: int
    columns: Optional[Any] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class StudentBase(BaseModel):
    matricula: str
    nome: str
    curso: Optional[str] = None
    turma: Optional[str] = None
    semestre: Optional[int] = None
    forma_ingresso: Optional[str] = None
    communication_opt_out: bool = False
    dias_atraso_boleto: Optional[int] = None
    recorrencia_atrasos: Optional[int] = None
    dias_sem_login: Optional[int] = None
    presenca_percentual: Optional[float] = None
    nota_media: Optional[float] = None
    reprovacoes: Optional[int] = None


class StudentCreate(StudentBase):
    batch_id: str
    raw_data: Optional[dict] = None


class StudentResponse(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    communication_opt_out: bool = False
    shap_top_factors: Optional[dict] = None
    created_at: datetime
    is_active: bool = True


class UploadResultResponse(BaseModel):
    message: str
    batch: UploadBatchResponse
    students_imported: int
    columns_detected: list[str]
    preview: list[dict] = Field(default_factory=list)
