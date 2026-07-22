"""
Schemas Pydantic del SSP.
Reflejan exactamente los tipos definidos en src/types/index.ts del frontend.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator

Role = Literal["ADMIN", "PROFESOR", "ALUMNO"]
AulaEstado = Literal["ACTIVA", "CONCLUIDA"]


# ── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    """Usuario público (sin password). Idéntico a la interfaz User del frontend."""

    id: str
    nombres: str
    apellidos: str
    email: EmailStr
    role: Role

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Idéntico a LoginResponse del frontend."""

    token: str
    user: UserOut


class RegisterRequest(BaseModel):
    """Idéntico a RegisterPayload del frontend."""

    nombres: str
    apellidos: str
    email: EmailStr
    password: str
    role: Role
    codigo: Optional[str] = None

    @field_validator("nombres", "apellidos", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


class RecoverRequest(BaseModel):
    email: EmailStr


class RecoverResponse(BaseModel):
    message: str


# ── Aulas ──────────────────────────────────────────────────────────────────────


class CreateAulaRequest(BaseModel):
    """Idéntico a CreateAulaPayload del frontend."""

    nombre: str
    codigo: str
    descripcion: str
    periodo: str

    @field_validator("nombre", "codigo", "descripcion", "periodo", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


class AulaOut(BaseModel):
    """Idéntico a la interfaz Aula del frontend."""

    id: str
    nombre: str
    codigo: str
    descripcion: str
    periodo: str
    profesorId: str
    profesorNombre: str
    estado: AulaEstado
    inscritos: int
    createdAt: str  # ISO 8601 string, como espera el frontend

    model_config = {"from_attributes": True}
