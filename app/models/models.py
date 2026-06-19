import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.db.session import Base

# ── Enums (deben coincidir con los tipos del frontend) ─────────────────────────

import enum


class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    PROFESOR = "PROFESOR"
    ALUMNO = "ALUMNO"


class AulaEstadoEnum(str, enum.Enum):
    ACTIVA = "ACTIVA"
    CONCLUIDA = "CONCLUIDA"


# ── Tablas ──────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: f"u-{uuid.uuid4().hex[:10]}")
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.ALUMNO)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    aulas = relationship("Aula", back_populates="profesor")


class Aula(Base):
    __tablename__ = "aulas"

    id = Column(String, primary_key=True, default=lambda: f"a-{uuid.uuid4().hex[:10]}")
    nombre = Column(String(200), nullable=False)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    descripcion = Column(Text, nullable=False, default="")
    periodo = Column(String(20), nullable=False)
    profesor_id = Column(String, ForeignKey("users.id"), nullable=False)
    estado = Column(Enum(AulaEstadoEnum), nullable=False, default=AulaEstadoEnum.ACTIVA)
    inscritos = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    profesor = relationship("User", back_populates="aulas")
