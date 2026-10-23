"""
Schemas Pydantic del SSP.
Reflejan exactamente los tipos definidos en src/types/index.ts del frontend.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, EmailStr, Field, StrictBool, StrictInt, field_validator, model_validator

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
    nombre: str = Field(min_length=1, max_length=200)
    codigo: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9-]+$")
    descripcion: str = Field(default="", max_length=4000)
    periodo: str = Field(min_length=1, max_length=20)
    profesorId: Optional[str] = None
    solicitudId: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9-]{16,80}$")

    @field_validator("nombre", "codigo", "descripcion", "periodo", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value


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
    anterior: Role


# ── Tareas y entregas (HU-09/10) ────────────────────────────────────────────


class EntregaOut(BaseModel):
    revision: int = 0
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
    revision: int = 0
    aulaId: str
    titulo: str
    descripcion: str
    fechaLimite: Optional[str]
    createdAt: str
    entrega: Optional[EntregaOut]


class CreateTareaRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(min_length=1, max_length=6000)
    fechaLimite: Optional[AwareDatetime] = None
    solicitudId: str = Field(pattern=r"^[a-zA-Z0-9-]{16,80}$")

    @field_validator("titulo", "descripcion")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Completa el título y las instrucciones.")
        return value


class SubmitEntregaRequest(BaseModel):
    descripcion: str = Field(default="", max_length=6000)
    comentario: str = Field(default="", max_length=2000)
    archivoId: Optional[str] = None

    @model_validator(mode="after")
    def content_required(self):
        self.descripcion = self.descripcion.strip()
        self.comentario = self.comentario.strip()
        if not self.descripcion and not self.archivoId:
            raise ValueError("Escribe tu respuesta antes de entregar.")
        return self


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
NotificacionTipo = Literal["TAREA_ASIGNADA", "VENCIMIENTO", "TAREA_ACTUALIZADA", "REVISION_HORAS"]


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
    revision: int
    observacion: str


class RegistrarHorasRequest(BaseModel):
    """Idéntico a RegistrarHorasPayload del frontend."""

    horas: StrictInt = Field(ge=1, le=24)
    descripcion: str = Field(min_length=1, max_length=2000)
    fecha: Optional[str] = None
    solicitudId: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9-]{16,80}$")

    @field_validator("descripcion")
    @classmethod
    def description_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Describe la actividad realizada.")
        return value


class CorregirHorasRequest(RegistrarHorasRequest):
    revision: StrictInt = Field(ge=0)
    fecha: str


class RevisarHorasRequest(BaseModel):
    estadoValidacion: Literal["VALIDADO", "RECHAZADO"]
    revision: StrictInt = Field(ge=0)
    observacion: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def reason_required(self):
        self.observacion = self.observacion.strip()
        if self.estadoValidacion == "RECHAZADO" and not self.observacion:
            raise ValueError("Explica qué debe corregir el alumno.")
        return self


class HistorialHorasOut(BaseModel):
    id: str
    revision: int
    userNombre: str
    accion: str
    fecha: str
    antes: Optional[RegistroHorasOut]
    despues: RegistroHorasOut


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


class DestinoTarea(BaseModel):
    tipo: Literal["TAREA"]
    aulaId: str = Field(min_length=1, max_length=200)
    tareaId: str = Field(min_length=1, max_length=200)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class DestinoActividad(BaseModel):
    tipo: Literal["ACTIVIDAD"]
    practicaId: str = Field(min_length=1, max_length=200)
    registroId: str = Field(min_length=1, max_length=200)
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class NotificacionOut(BaseModel):
    """Idéntico a la interfaz Notificacion del frontend."""

    id: str
    userId: str
    tipo: NotificacionTipo
    titulo: str
    mensaje: str
    leida: bool
    fecha: str
    destino: DestinoTarea | DestinoActividad | None = Field(default=None, discriminator="tipo")


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


class SolicitudContenido(BaseModel):
    solicitudId: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9-]{16,80}$")

    @field_validator("titulo", "mensaje", "texto", "descripcion", mode="before", check_fields=False)
    @classmethod
    def trim_content(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("El contenido no puede estar vacío.")
        return value


class CreateMetaRequest(SolicitudContenido):
    """Idéntico a CreateMetaPayload del frontend."""

    tipo: MetaTipo
    cantidadObjetivo: StrictInt = Field(ge=1, le=1000000)
    descripcion: Optional[str] = Field(default=None, max_length=2000)


class RegistrarAvanceMetaRequest(BaseModel):
    """Idéntico a RegistrarAvanceMetaPayload del frontend."""

    cantidad: int


class EstablecerAvanceMetaRequest(BaseModel):
    cantidad: StrictInt = Field(ge=0, le=1000000)
    anterior: StrictInt = Field(ge=0, le=1000000)
    motivo: str = Field(min_length=1, max_length=2000)

    @field_validator("motivo")
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError("Describe la producción revisada.")
        return value.strip()


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
    registrado: bool


class AsistenciaSesionOut(BaseModel):
    """Estado de asistencia de un aula en una fecha concreta."""

    aulaId: str
    fecha: str
    items: list[AsistenciaItemOut]
    versionAsistencia: Literal[1] = 1
    estadoRegistro: Literal["PROPUESTO", "GUARDADO", "PARCIAL"]
    revision: str


class AsistenciaItemIn(BaseModel):
    practicanteId: str
    presente: StrictBool


class GuardarAsistenciaRequest(BaseModel):
    fecha: str  # ISO date (YYYY-MM-DD)
    items: list[AsistenciaItemIn]
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")


# ── Docencia del profesor: revisar y calificar entregas (HU-26) ───────────────


class EntregaProfesorOut(BaseModel):
    revision: int = 0
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
    revisionEntrega: Optional[StrictInt] = Field(default=None, ge=0)
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
    anterior: AulaEstado


class AsignarProfesorRequest(BaseModel):
    profesorId: str
    anterior: str


class MatriculaAlumnoOut(BaseModel):
    alumnoId: str
    alumnoNombre: str
    email: str
    inscrito: bool


class MatriculasOut(BaseModel):
    revision: str
    aulaId: str
    aulaNombre: str
    alumnos: list[MatriculaAlumnoOut]


class MatricularRequest(BaseModel):
    alumnoId: str


class EstablecerMatriculaRequest(BaseModel):
    inscrito: StrictBool
    revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")


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


class CreateAnuncioRequest(SolicitudContenido):
    titulo: str = Field(min_length=1, max_length=200)
    mensaje: str = Field(min_length=1, max_length=10000)
    fijado: StrictBool = False


# ── Comunicación: foros (HU-37) ───────────────────────────────────────────────


class ForoHiloOut(BaseModel):
    id: str
    aulaId: str
    autorNombre: str
    titulo: str
    respuestas: int
    fecha: str


class CreateHiloRequest(SolicitudContenido):
    titulo: str = Field(min_length=1, max_length=200)


class ForoMensajeOut(BaseModel):
    id: str
    hiloId: str
    autorNombre: str
    texto: str
    fecha: str


class CreateForoMensajeRequest(SolicitudContenido):
    texto: str = Field(min_length=1, max_length=10000)


# ── Comunicación: mensajería directa (HU-38) ──────────────────────────────────


class ContactoOut(BaseModel):
    userId: str
    nombre: str
    aulaId: str
    aulaNombre: str
    noLeidos: int


class MensajeDirectoOut(BaseModel):
    aulaId: str
    destinatarioId: str
    leido: bool
    id: str
    remitenteId: str
    remitenteNombre: str
    texto: str
    mio: bool
    fecha: str


class EnviarMensajeRequest(SolicitudContenido):
    texto: str = Field(min_length=1, max_length=10000)


class LeerMensajesRequest(BaseModel):
    mensajeIds: list[str] = Field(min_length=1, max_length=200)

    @field_validator("mensajeIds")
    @classmethod
    def distinct_ids(cls, values):
        if len(set(values)) != len(values) or any(not v.strip() for v in values):
            raise ValueError("Selecciona mensajes distintos y válidos.")
        return values
