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
    SUPERVISOR = "SUPERVISOR"


class AulaEstadoEnum(str, enum.Enum):
    ACTIVA = "ACTIVA"
    CONCLUIDA = "CONCLUIDA"


class ActividadEstadoEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    SIN_LEER = "SIN_LEER"
    CALIFICADA = "CALIFICADA"


class EntregaEstadoEnum(str, enum.Enum):
    ENTREGADA = "ENTREGADA"
    CALIFICADA = "CALIFICADA"


class PracticaEstadoEnum(str, enum.Enum):
    EN_CURSO = "EN_CURSO"
    LISTA_PARA_CIERRE = "LISTA_PARA_CIERRE"
    CERRADA = "CERRADA"


class NotificacionTipoEnum(str, enum.Enum):
    TAREA_ASIGNADA = "TAREA_ASIGNADA"
    VENCIMIENTO = "VENCIMIENTO"


class RegistroHorasEstadoEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    VALIDADO = "VALIDADO"
    RECHAZADO = "RECHAZADO"


class MetaTipoEnum(str, enum.Enum):
    ARTICULOS = "ARTICULOS"
    NOTAS_PERIODISTICAS = "NOTAS_PERIODISTICAS"
    NOTAS_PRENSA = "NOTAS_PRENSA"
    HORAS = "HORAS"


class EvaluacionEstadoEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    COMPLETADA = "COMPLETADA"


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


class Inscripcion(Base):
    """Matrícula de un alumno en un aula, con su avance (HU-05)."""

    __tablename__ = "inscripciones"

    id = Column(String, primary_key=True, default=lambda: f"i-{uuid.uuid4().hex[:10]}")
    alumno_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    progreso = Column(Integer, nullable=False, default=0)  # 0–100
    semana_actual = Column(Integer, nullable=False, default=0)
    semanas_totales = Column(Integer, nullable=False, default=16)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    alumno = relationship("User")
    aula = relationship("Aula")


class Archivo(Base):
    """Archivo subido a un aula (HU-07/08)."""

    __tablename__ = "archivos"

    id = Column(String, primary_key=True, default=lambda: f"arc-{uuid.uuid4().hex[:8]}")
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    subido_por_id = Column(String, ForeignKey("users.id"), nullable=False)
    nombre_original = Column(String(255), nullable=False)
    nombre_guardado = Column(String(255), unique=True, nullable=False)
    tipo_mime = Column(String(100), nullable=False)
    tamanio = Column(Integer, nullable=False)  # bytes
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    aula = relationship("Aula")
    subido_por = relationship("User", foreign_keys=[subido_por_id])


class Tarea(Base):
    """Tarea asignada a un aula por el profesor (HU-09)."""

    __tablename__ = "tareas"

    id = Column(String, primary_key=True, default=lambda: f"t-{uuid.uuid4().hex[:8]}")
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=False, default="")
    fecha_limite = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    aula = relationship("Aula")
    entregas = relationship("Entrega", back_populates="tarea")


class Entrega(Base):
    """Entrega de un alumno a una tarea (HU-09)."""

    __tablename__ = "entregas"

    id = Column(String, primary_key=True, default=lambda: f"ent-{uuid.uuid4().hex[:8]}")
    tarea_id = Column(String, ForeignKey("tareas.id"), nullable=False, index=True)
    alumno_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    descripcion = Column(Text, nullable=False, default="")
    comentario = Column(Text, nullable=False, default="")
    archivo_id = Column(String, ForeignKey("archivos.id"), nullable=True)
    estado = Column(
        Enum(EntregaEstadoEnum),
        nullable=False,
        default=EntregaEstadoEnum.ENTREGADA,
    )
    nota = Column(Integer, nullable=True)        # 0–20
    retroalimentacion = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    tarea = relationship("Tarea", back_populates="entregas")
    alumno = relationship("User", foreign_keys=[alumno_id])
    archivo = relationship("Archivo")


class ActividadReciente(Base):
    """Ítem del feed de actividad reciente de un alumno (HU-05)."""

    __tablename__ = "actividad_reciente"

    id = Column(String, primary_key=True, default=lambda: f"act-{uuid.uuid4().hex[:8]}")
    alumno_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    contexto = Column(String(255), nullable=False, default="")
    tiempo = Column(String(60), nullable=False, default="")
    estado = Column(Enum(ActividadEstadoEnum), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    alumno = relationship("User")


class Empresa(Base):
    """Centro de prácticas registrado por un practicante (HU-13)."""

    __tablename__ = "empresas"

    id = Column(String, primary_key=True, default=lambda: f"e-{uuid.uuid4().hex[:10]}")
    practicante_id = Column(
        String, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    razon_social = Column(String(200), nullable=False)
    ruc = Column(String(20), nullable=False)
    direccion = Column(String(255), nullable=False, default="")
    sector = Column(String(120), nullable=False, default="")
    telefono = Column(String(40), nullable=False, default="")
    email = Column(String(255), nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    practicante = relationship("User")
    supervisor = relationship("Supervisor", back_populates="empresa", uselist=False)


class Supervisor(Base):
    """Supervisor externo asignado en la empresa de prácticas (HU-19)."""

    __tablename__ = "supervisores"

    id = Column(String, primary_key=True, default=lambda: f"s-{uuid.uuid4().hex[:10]}")
    empresa_id = Column(
        String, ForeignKey("empresas.id"), nullable=False, unique=True, index=True
    )
    # Vincula este contacto con una cuenta de login (rol SUPERVISOR, HU-24).
    user_id = Column(String, ForeignKey("users.id"), nullable=True, unique=True, index=True)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    cargo = Column(String(120), nullable=False, default="")
    email = Column(String(255), nullable=False, default="")
    telefono = Column(String(40), nullable=False, default="")

    empresa = relationship("Empresa", back_populates="supervisor")


class Practica(Base):
    """
    Ciclo de prácticas de un alumno en un aula/periodo. Entidad central de
    seguimiento de horas (HU-14), cierre/validación (HU-15) e historial (HU-18).
    """

    __tablename__ = "practicas"

    id = Column(String, primary_key=True, default=lambda: f"pr-{uuid.uuid4().hex[:10]}")
    practicante_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    periodo = Column(String(20), nullable=False)
    empresa_id = Column(String, ForeignKey("empresas.id"), nullable=True)
    horas_acumuladas = Column(Integer, nullable=False, default=0)
    horas_minimas = Column(Integer, nullable=False, default=360)
    estado = Column(
        Enum(PracticaEstadoEnum),
        nullable=False,
        default=PracticaEstadoEnum.EN_CURSO,
    )
    fecha_inicio = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    fecha_cierre = Column(DateTime(timezone=True), nullable=True)
    validado_por = Column(String(200), nullable=True)

    practicante = relationship("User")
    aula = relationship("Aula")
    empresa = relationship("Empresa")
    registros_horas = relationship("RegistroHoras", back_populates="practica")


class RegistroHoras(Base):
    """Registro individual de horas trabajadas dentro de una práctica (HU-14)."""

    __tablename__ = "registro_horas"

    id = Column(String, primary_key=True, default=lambda: f"h-{uuid.uuid4().hex[:10]}")
    practica_id = Column(String, ForeignKey("practicas.id"), nullable=False, index=True)
    fecha = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    horas = Column(Integer, nullable=False)
    descripcion = Column(Text, nullable=False, default="")
    estado_validacion = Column(
        Enum(RegistroHorasEstadoEnum),
        nullable=False,
        default=RegistroHorasEstadoEnum.PENDIENTE,
    )

    practica = relationship("Practica", back_populates="registros_horas")


class Notificacion(Base):
    """Notificación de tarea asignada o vencimiento próximo (HU-17)."""

    __tablename__ = "notificaciones"

    id = Column(String, primary_key=True, default=lambda: f"n-{uuid.uuid4().hex[:10]}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    tipo = Column(Enum(NotificacionTipoEnum), nullable=False)
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text, nullable=False, default="")
    leida = Column(Integer, nullable=False, default=0)  # 0 / 1 (bool en SQLite)
    fecha = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user = relationship("User")


class Meta(Base):
    """Meta cuantitativa definida por el asesor para medir el avance real de un practicante (HU-20/21)."""

    __tablename__ = "metas"

    id = Column(String, primary_key=True, default=lambda: f"m-{uuid.uuid4().hex[:10]}")
    practica_id = Column(String, ForeignKey("practicas.id"), nullable=False, index=True)
    tipo = Column(Enum(MetaTipoEnum), nullable=False)
    cantidad_objetivo = Column(Integer, nullable=False)
    cantidad_alcanzada = Column(Integer, nullable=False, default=0)
    descripcion = Column(Text, nullable=True)
    creado_por = Column(String(200), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    practica = relationship("Practica")


class RegistroAsistencia(Base):
    """Registro de asistencia diaria de un practicante a su aula/práctica (HU-22)."""

    __tablename__ = "asistencias"

    id = Column(String, primary_key=True, default=lambda: f"as-{uuid.uuid4().hex[:8]}")
    practicante_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    fecha = Column(DateTime(timezone=True), nullable=False)
    presente = Column(Integer, nullable=False, default=1)  # 0 / 1 (bool en SQLite)

    practicante = relationship("User")
    aula = relationship("Aula")


class Anuncio(Base):
    """Anuncio publicado por el profesor en un aula (HU-36)."""

    __tablename__ = "anuncios"

    id = Column(String, primary_key=True, default=lambda: f"an-{uuid.uuid4().hex[:10]}")
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    autor_id = Column(String, ForeignKey("users.id"), nullable=False)
    autor_nombre = Column(String(200), nullable=False)
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text, nullable=False, default="")
    fijado = Column(Integer, nullable=False, default=0)  # 0 / 1
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    autor = relationship("User")


class ForoHilo(Base):
    """Hilo de discusión de un aula (HU-37)."""

    __tablename__ = "foro_hilos"

    id = Column(String, primary_key=True, default=lambda: f"fh-{uuid.uuid4().hex[:10]}")
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    autor_id = Column(String, ForeignKey("users.id"), nullable=False)
    autor_nombre = Column(String(200), nullable=False)
    titulo = Column(String(200), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    autor = relationship("User")
    mensajes = relationship("ForoMensaje", back_populates="hilo")


class ForoMensaje(Base):
    """Respuesta dentro de un hilo del foro (HU-37)."""

    __tablename__ = "foro_mensajes"

    id = Column(String, primary_key=True, default=lambda: f"fm-{uuid.uuid4().hex[:10]}")
    hilo_id = Column(String, ForeignKey("foro_hilos.id"), nullable=False, index=True)
    autor_id = Column(String, ForeignKey("users.id"), nullable=False)
    autor_nombre = Column(String(200), nullable=False)
    texto = Column(Text, nullable=False, default="")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    hilo = relationship("ForoHilo", back_populates="mensajes")
    autor = relationship("User")


class MensajeDirecto(Base):
    """Mensaje directo entre profesor y alumno dentro de un aula (HU-38)."""

    __tablename__ = "mensajes_directos"

    id = Column(String, primary_key=True, default=lambda: f"md-{uuid.uuid4().hex[:10]}")
    aula_id = Column(String, ForeignKey("aulas.id"), nullable=False, index=True)
    remitente_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    destinatario_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    texto = Column(Text, nullable=False, default="")
    leido = Column(Integer, nullable=False, default=0)  # 0 / 1
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    remitente = relationship("User", foreign_keys=[remitente_id])
    destinatario = relationship("User", foreign_keys=[destinatario_id])


class Auditoria(Base):
    """Registro de acciones sensibles del administrador (HU-33)."""

    __tablename__ = "auditoria"

    id = Column(String, primary_key=True, default=lambda: f"au-{uuid.uuid4().hex[:10]}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    user_nombre = Column(String(200), nullable=False)
    accion = Column(String(80), nullable=False)
    detalle = Column(Text, nullable=False, default="")
    fecha = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    user = relationship("User")


class Evaluacion(Base):
    """Evaluación de desempeño de un practicante por su supervisor externo (HU-24)."""

    __tablename__ = "evaluaciones"

    id = Column(String, primary_key=True, default=lambda: f"ev-{uuid.uuid4().hex[:8]}")
    practica_id = Column(String, ForeignKey("practicas.id"), nullable=False, index=True)
    empresa_id = Column(String, ForeignKey("empresas.id"), nullable=False, index=True)
    periodo = Column(String(20), nullable=False)
    estado = Column(
        Enum(EvaluacionEstadoEnum), nullable=False, default=EvaluacionEstadoEnum.PENDIENTE
    )
    fecha_limite = Column(DateTime(timezone=True), nullable=True)

    practica = relationship("Practica")
    empresa = relationship("Empresa")
