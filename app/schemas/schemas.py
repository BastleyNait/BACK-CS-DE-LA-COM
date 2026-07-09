"""
Schemas Pydantic del SSP.
Reflejan exactamente los tipos definidos en src/types/index.ts del frontend.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator

Role = Literal["ADMIN", "PROFESOR", "ALUMNO"]
AulaEstado = Literal["ACTIVA", "CONCLUIDA"]
ActividadEstado = Literal["PENDIENTE", "SIN_LEER", "CALIFICADA"]


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


# ── Alumno (HU-05) ───────────────────────────────────────────────────────────


class AulaAlumnoOut(BaseModel):
    """Idéntico a la interfaz AulaAlumno del frontend."""

    id: str
    nombre: str
    profesorNombre: str
    ciclo: str
    estado: AulaEstado
    progreso: int
    semanaActual: int
    semanasTotales: int


class ActividadRecienteOut(BaseModel):
    """Idéntico a la interfaz ActividadReciente del frontend."""

    id: str
    titulo: str
    contexto: str
    tiempo: str
    estado: ActividadEstado


# ── Profesor (HU-11) ─────────────────────────────────────────────────────────


class PracticanteProgresoOut(BaseModel):
    alumnoId: str
    alumnoNombre: str
    alumnoEmail: str
    aulaId: str
    aulaNombre: str
    progreso: int
    semanaActual: int
    semanasTotales: int
    estado: AulaEstado
    tareasEntregadas: int
    tareasTotal: int


# ── Admin (HU-12) ─────────────────────────────────────────────────────────────


class UsuarioAdminOut(BaseModel):
    id: str
    nombres: str
    apellidos: str
    email: str
    role: Role
    createdAt: str


class UpdateRolRequest(BaseModel):
    role: Role


# ── Tareas y entregas (HU-09/10) ────────────────────────────────────────────


class EntregaOut(BaseModel):
    id: str
    tareaId: str
    alumnoId: str
    descripcion: str
    comentario: str
    archivoId: Optional[str]
    estado: str
    nota: Optional[int]
    retroalimentacion: Optional[str]
    createdAt: str


class TareaAlumnoOut(BaseModel):
    """Tarea vista desde el alumno, incluyendo su entrega si ya existe."""

    id: str
    aulaId: str
    titulo: str
    descripcion: str
    fechaLimite: Optional[str]
    createdAt: str
    entrega: Optional[EntregaOut]


class SubmitEntregaRequest(BaseModel):
    descripcion: str = ""
    comentario: str = ""
    archivoId: Optional[str] = None


class DetalleCalificacionOut(BaseModel):
    tareaId: str
    tareaTitulo: str
    nota: Optional[int]
    retroalimentacion: Optional[str]
    estado: str
    entregadaEn: Optional[str]


class CalificacionesOut(BaseModel):
    promedio: Optional[float]
    tareasTotal: int
    tareasEntregadas: int
    detalle: list[DetalleCalificacionOut]


# ── Archivos (HU-07/08) ──────────────────────────────────────────────────────


class ArchivoOut(BaseModel):
    """Idéntico a la interfaz Archivo del frontend."""

    id: str
    aulaId: str
    subidoPorId: str
    subidoPorNombre: str
    nombreOriginal: str
    tipoMime: str
    tamanio: int
    createdAt: str


# ── Empresa / centro de prácticas (HU-13) ─────────────────────────────────────

PracticaEstado = Literal["EN_CURSO", "LISTA_PARA_CIERRE", "CERRADA"]
NotificacionTipo = Literal["TAREA_ASIGNADA", "VENCIMIENTO"]


class EmpresaOut(BaseModel):
    """Idéntico a la interfaz Empresa del frontend."""

    id: str
    practicanteId: str
    razonSocial: str
    ruc: str
    direccion: str
    sector: str
    telefono: str
    email: str
    fechaRegistro: str


class CreateEmpresaRequest(BaseModel):
    """Idéntico a CreateEmpresaPayload del frontend."""

    razonSocial: str
    ruc: str
    direccion: str
    sector: str
    telefono: str
    email: EmailStr

    @field_validator(
        "razonSocial", "ruc", "direccion", "sector", "telefono", mode="before"
    )
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


# ── Supervisor externo (HU-19) ────────────────────────────────────────────────


class SupervisorOut(BaseModel):
    """Idéntico a la interfaz Supervisor del frontend."""

    id: str
    empresaId: str
    nombres: str
    apellidos: str
    cargo: str
    email: str
    telefono: str


class CreateSupervisorRequest(BaseModel):
    """Idéntico a CreateSupervisorPayload del frontend."""

    nombres: str
    apellidos: str
    cargo: str
    email: EmailStr
    telefono: str

    @field_validator("nombres", "apellidos", "cargo", "telefono", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


# ── Prácticas: horas, cierre, historial (HU-14/15/18) ─────────────────────────


class PracticaOut(BaseModel):
    """Idéntico a la interfaz Practica del frontend."""

    id: str
    practicanteId: str
    practicanteNombre: str
    aulaId: str
    aulaNombre: str
    periodo: str
    empresaId: Optional[str] = None
    horasAcumuladas: int
    horasMinimas: int
    estado: PracticaEstado
    fechaInicio: str
    fechaCierre: Optional[str] = None
    validadoPor: Optional[str] = None


class RegistroHorasOut(BaseModel):
    """Idéntico a la interfaz RegistroHoras del frontend."""

    id: str
    practicaId: str
    fecha: str
    horas: int
    descripcion: str


class RegistrarHorasRequest(BaseModel):
    """Idéntico a RegistrarHorasPayload del frontend."""

    horas: int
    descripcion: str
    fecha: Optional[str] = None


class RegistrarHorasResponse(BaseModel):
    """Respuesta de registrar horas: práctica actualizada + registro creado."""

    practica: PracticaOut
    registro: RegistroHorasOut


# ── Reporte final (HU-16) ─────────────────────────────────────────────────────


class ReporteFinalOut(BaseModel):
    """Idéntico a la interfaz ReporteFinal del frontend."""

    id: str
    practicaId: str
    generadoPor: str
    generadoEn: str
    contenido: str


# ── Notificaciones (HU-17) ────────────────────────────────────────────────────


class NotificacionOut(BaseModel):
    """Idéntico a la interfaz Notificacion del frontend."""

    id: str
    userId: str
    tipo: NotificacionTipo
    titulo: str
    mensaje: str
    leida: bool
    fecha: str
