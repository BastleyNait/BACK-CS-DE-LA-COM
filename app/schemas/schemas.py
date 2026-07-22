"""
Schemas Pydantic del SSP.
Reflejan exactamente los tipos definidos en src/types/index.ts del frontend.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, field_validator

Role = Literal["ADMIN", "PROFESOR", "ALUMNO", "SUPERVISOR"]
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
    userId: Optional[str] = None
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


RegistroHorasEstado = Literal["PENDIENTE", "VALIDADO", "RECHAZADO"]


class RegistroHorasOut(BaseModel):
    """Idéntico a la interfaz RegistroHoras del frontend."""

    id: str
    practicaId: str
    fecha: str
    horas: int
    descripcion: str
    estadoValidacion: RegistroHorasEstado


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


# ── Metas por practicante (HU-20/21) ──────────────────────────────────────────

MetaTipo = Literal["ARTICULOS", "NOTAS_PERIODISTICAS", "NOTAS_PRENSA", "HORAS"]


class MetaOut(BaseModel):
    """Idéntico a la interfaz Meta del frontend."""

    id: str
    practicaId: str
    practicanteId: str
    practicanteNombre: str
    tipo: MetaTipo
    cantidadObjetivo: int
    cantidadAlcanzada: int
    descripcion: Optional[str] = None
    creadoPor: str
    fechaCreacion: str


class CreateMetaRequest(BaseModel):
    """Idéntico a CreateMetaPayload del frontend."""

    tipo: MetaTipo
    cantidadObjetivo: int
    descripcion: Optional[str] = None


class RegistrarAvanceMetaRequest(BaseModel):
    """Idéntico a RegistrarAvanceMetaPayload del frontend."""

    cantidad: int


# ── Asistencia (soporte de HU-22) ─────────────────────────────────────────────


class RegistroAsistenciaOut(BaseModel):
    """Idéntico a la interfaz RegistroAsistencia del frontend."""

    id: str
    practicanteId: str
    aulaId: str
    fecha: str
    presente: bool


# ── Evaluaciones (soporte de HU-24) ───────────────────────────────────────────

EvaluacionEstado = Literal["PENDIENTE", "COMPLETADA"]


class EvaluacionOut(BaseModel):
    """Idéntico a la interfaz Evaluacion del frontend."""

    id: str
    practicaId: str
    practicanteId: str
    practicanteNombre: str
    empresaId: str
    periodo: str
    estado: EvaluacionEstado
    fechaLimite: str


# ── Paneles de control por rol (HU-22/23/24) ──────────────────────────────────


class AlumnoEnRiesgoOut(BaseModel):
    practicanteId: str
    practicanteNombre: str
    motivos: list[str]


class ResumenProfesorOut(BaseModel):
    alumnosActivos: int
    entregasPendientes: int
    asistenciaPromedio: Optional[int] = None
    alumnosEnRiesgo: list[AlumnoEnRiesgoOut]


class ResumenAdminOut(BaseModel):
    alumnosMatriculados: int
    profesoresActivos: int
    aulasActivas: int
    centrosDePracticas: int


class ResumenEmpresaOut(BaseModel):
    practicantesActivos: int
    horasPorValidar: int
    evaluacionesPendientes: int
    cumplimientoPromedio: Optional[int] = None


# ── Docencia del profesor: asistencia (HU-25) ─────────────────────────────────


class AsistenciaItemOut(BaseModel):
    practicanteId: str
    practicanteNombre: str
    presente: bool


class AsistenciaSesionOut(BaseModel):
    """Estado de asistencia de un aula en una fecha concreta."""

    aulaId: str
    fecha: str
    items: list[AsistenciaItemOut]


class AsistenciaItemIn(BaseModel):
    practicanteId: str
    presente: bool


class GuardarAsistenciaRequest(BaseModel):
    fecha: str  # ISO date (YYYY-MM-DD)
    items: list[AsistenciaItemIn]


# ── Docencia del profesor: revisar y calificar entregas (HU-26) ───────────────


class EntregaProfesorOut(BaseModel):
    """Entrega vista por el profesor, con datos del alumno y la tarea."""

    id: str
    tareaId: str
    tareaTitulo: str
    alumnoId: str
    alumnoNombre: str
    descripcion: str
    comentario: str
    archivoId: Optional[str]
    estado: str
    nota: Optional[int]
    retroalimentacion: Optional[str]
    createdAt: str


class CalificarEntregaRequest(BaseModel):
    nota: int
    retroalimentacion: str = ""

    @field_validator("nota")
    @classmethod
    def nota_en_rango(cls, v: int) -> int:
        if v < 0 or v > 20:
            raise ValueError("La nota debe estar entre 0 y 20.")
        return v


# ── Docencia del profesor: libro de calificaciones (HU-27) ────────────────────


class LibroTareaOut(BaseModel):
    id: str
    titulo: str


class LibroAlumnoOut(BaseModel):
    alumnoId: str
    alumnoNombre: str
    codigo: str
    notas: dict[str, Optional[int]]  # tareaId -> nota (o None)
    promedio: Optional[float]
    asistenciaPct: Optional[int]
    horas: int


class LibroCalificacionesOut(BaseModel):
    aulaId: str
    aulaNombre: str
    tareas: list[LibroTareaOut]
    alumnos: list[LibroAlumnoOut]
    promedioGeneral: Optional[float]


# ── Docencia del profesor: seguimiento individual (HU-28) ─────────────────────


class SeguimientoEntregaOut(BaseModel):
    tareaTitulo: str
    nota: Optional[int]
    estado: str
    retroalimentacion: Optional[str]


class SeguimientoOut(BaseModel):
    practicanteId: str
    practicanteNombre: str
    practicanteEmail: str
    aulaId: str
    aulaNombre: str
    empresaNombre: Optional[str]
    promedio: Optional[float]
    asistenciaPct: Optional[int]
    horasAcumuladas: int
    horasMinimas: int
    progreso: int
    estadoPractica: Optional[str]
    entregas: list[SeguimientoEntregaOut]
    motivosRiesgo: list[str]


# ── Gestión administrativa de aulas y matrículas (HU-29/30/31) ────────────────


class UpdateAulaEstadoRequest(BaseModel):
    estado: AulaEstado


class AsignarProfesorRequest(BaseModel):
    profesorId: str


class MatriculaAlumnoOut(BaseModel):
    alumnoId: str
    alumnoNombre: str
    email: str
    inscrito: bool


class MatriculasOut(BaseModel):
    aulaId: str
    aulaNombre: str
    alumnos: list[MatriculaAlumnoOut]


class MatricularRequest(BaseModel):
    alumnoId: str


# ── Reportes institucionales (HU-32) ──────────────────────────────────────────


class ReporteAulaOut(BaseModel):
    aulaId: str
    aulaNombre: str
    periodo: str
    profesorNombre: str
    estado: AulaEstado
    inscritos: int
    promedioNotas: Optional[float]
    asistenciaPct: Optional[int]


class ReporteInstitucionalOut(BaseModel):
    totalAlumnos: int
    totalProfesores: int
    totalAulas: int
    aulasActivas: int
    practicasEnCurso: int
    practicasCerradas: int
    horasPromedio: Optional[float]
    aulas: list[ReporteAulaOut]


# ── Auditoría (HU-33) ─────────────────────────────────────────────────────────


class AuditoriaOut(BaseModel):
    id: str
    userNombre: str
    accion: str
    detalle: str
    fecha: str


# ── Comunicación: anuncios (HU-36) ────────────────────────────────────────────


class AnuncioOut(BaseModel):
    id: str
    aulaId: str
    autorNombre: str
    titulo: str
    mensaje: str
    fijado: bool
    fecha: str


class CreateAnuncioRequest(BaseModel):
    titulo: str
    mensaje: str
    fijado: bool = False

    @field_validator("titulo", "mensaje", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


# ── Comunicación: foros (HU-37) ───────────────────────────────────────────────


class ForoHiloOut(BaseModel):
    id: str
    aulaId: str
    autorNombre: str
    titulo: str
    respuestas: int
    fecha: str


class CreateHiloRequest(BaseModel):
    titulo: str


class ForoMensajeOut(BaseModel):
    id: str
    hiloId: str
    autorNombre: str
    texto: str
    fecha: str


class CreateForoMensajeRequest(BaseModel):
    texto: str


# ── Comunicación: mensajería directa (HU-38) ──────────────────────────────────


class ContactoOut(BaseModel):
    userId: str
    nombre: str
    aulaId: str
    aulaNombre: str
    noLeidos: int


class MensajeDirectoOut(BaseModel):
    id: str
    remitenteId: str
    remitenteNombre: str
    texto: str
    mio: bool
    fecha: str


class EnviarMensajeRequest(BaseModel):
    texto: str
