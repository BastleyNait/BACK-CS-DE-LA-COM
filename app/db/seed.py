"""
Script de semilla — inserta los datos iniciales del mockDb.
Es idempotente por bloque: puede re-ejecutarse tras añadir tablas nuevas y
solo insertará lo que aún falte.
    python -m app.db.seed
"""

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.models import (
    ActividadEstadoEnum,
    ActividadReciente,
    Aula,
    AulaEstadoEnum,
    Base,
    Empresa,
    Entrega,
    EntregaEstadoEnum,
    Inscripcion,
    Notificacion,
    NotificacionTipoEnum,
    Practica,
    PracticaEstadoEnum,
    RegistroHoras,
    RoleEnum,
    Supervisor,
    Tarea,
    User,
)
from datetime import datetime, timedelta, timezone


def _seed_base(db) -> None:
    """Usuarios, aulas, inscripciones, actividad, tareas y entregas (HU-01..10)."""
    if db.query(User).count() > 0:
        return

    # ── Usuarios semilla (idénticos al mockDb del frontend) ────────────────────
    admin = User(
        id="u-admin",
        nombres="Gabriel",
        apellidos="Llerena",
        email="admin@unsa.edu.pe",
        hashed_password=hash_password("admin123"),
        role=RoleEnum.ADMIN,
    )
    profesor = User(
        id="u-prof",
        nombres="Jose Luis",
        apellidos="Cuenca",
        email="profesor@unsa.edu.pe",
        hashed_password=hash_password("profesor123"),
        role=RoleEnum.PROFESOR,
    )
    alumno = User(
        id="u-alumno",
        nombres="Piero",
        apellidos="Mejía",
        email="alumno@unsa.edu.pe",
        hashed_password=hash_password("alumno123"),
        role=RoleEnum.ALUMNO,
    )
    db.add_all([admin, profesor, alumno])
    db.flush()  # necesario para FK en aulas

    # ── Aulas semilla ──────────────────────────────────────────────────────────
    aula1 = Aula(
        id="a-1",
        nombre="Prácticas Pre-Profesionales I",
        codigo="PP-2026-I",
        descripcion="Seguimiento de prácticas en empresas convenio. Registro de asistencia e informes semanales.",
        periodo="2026-I",
        profesor_id="u-prof",
        estado=AulaEstadoEnum.ACTIVA,
        inscritos=18,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    aula2 = Aula(
        id="a-2",
        nombre="Taller de Comunicación Audiovisual",
        codigo="TCA-2025-II",
        descripcion="Curso concluido del periodo anterior.",
        periodo="2025-II",
        profesor_id="u-prof",
        estado=AulaEstadoEnum.CONCLUIDA,
        inscritos=24,
        created_at=datetime(2025, 8, 15, tzinfo=timezone.utc),
    )
    db.add_all([aula1, aula2])
    db.flush()  # necesario para FK en inscripciones

    # ── Inscripciones del alumno (HU-05) ───────────────────────────────────────
    db.add_all(
        [
            Inscripcion(
                alumno_id="u-alumno",
                aula_id="a-1",
                progreso=65,
                semana_actual=9,
                semanas_totales=16,
            ),
            Inscripcion(
                alumno_id="u-alumno",
                aula_id="a-2",
                progreso=100,
                semana_actual=16,
                semanas_totales=16,
            ),
        ]
    )

    # ── Actividad reciente del alumno (HU-05) ──────────────────────────────────
    db.add_all(
        [
            ActividadReciente(
                alumno_id="u-alumno",
                titulo="Informe semanal N.° 9 publicado",
                contexto="Prácticas Pre-Profesionales I — hace 2 horas",
                tiempo="hace 2 horas",
                estado=ActividadEstadoEnum.PENDIENTE,
            ),
            ActividadReciente(
                alumno_id="u-alumno",
                titulo="Nuevo mensaje del profesor",
                contexto="Jose Luis Cuenca — ayer",
                tiempo="ayer",
                estado=ActividadEstadoEnum.SIN_LEER,
            ),
            ActividadReciente(
                alumno_id="u-alumno",
                titulo="Tarea N.° 8 calificada: 17/20",
                contexto="Prácticas Pre-Profesionales I — hace 3 días",
                tiempo="hace 3 días",
                estado=ActividadEstadoEnum.CALIFICADA,
            ),
        ]
    )

    # ── Tareas del aula activa (HU-09) ─────────────────────────────────────────
    tarea1 = Tarea(
        id="t-1",
        aula_id="a-1",
        titulo="Informe Semanal N.° 8",
        descripcion="Redacta el informe correspondiente a la semana 8 de prácticas, incluyendo las actividades realizadas, horas trabajadas y evidencias.",
        fecha_limite=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    tarea2 = Tarea(
        id="t-2",
        aula_id="a-1",
        titulo="Informe Semanal N.° 9",
        descripcion="Redacta el informe de la semana 9 con evidencias fotográficas o capturas de pantalla adjuntas como archivo.",
        fecha_limite=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )
    tarea3 = Tarea(
        id="t-3",
        aula_id="a-1",
        titulo="Plan de Trabajo Final",
        descripcion="Presenta tu plan de trabajo para las semanas restantes de práctica, indicando objetivos, actividades y cronograma.",
        fecha_limite=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db.add_all([tarea1, tarea2, tarea3])
    db.flush()

    # Entrega calificada (tarea1 ya fue revisada por el profesor)
    db.add(
        Entrega(
            id="ent-1",
            tarea_id="t-1",
            alumno_id="u-alumno",
            descripcion="Adjunto mi informe de la semana 8 con todas las actividades realizadas en el área de producción audiovisual.",
            comentario="Esta semana trabajé en el montaje del spot publicitario para el cliente principal.",
            estado=EntregaEstadoEnum.CALIFICADA,
            nota=17,
            retroalimentacion="Excelente presentación. Buena estructura y detalle en las actividades. Continúa así.",
            created_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        )
    )
    print("[OK] Datos base (usuarios/aulas/tareas) insertados.")


def _seed_practicas(db) -> None:
    """Empresa, supervisor, prácticas y bitácora de horas (HU-13/14/15/18/19)."""
    if db.query(Practica).count() > 0:
        return

    # ── Empresa y supervisor externo (HU-13 / HU-19) ───────────────────────────
    db.add(
        Empresa(
            id="e-1",
            practicante_id="u-alumno",
            razon_social="Radio Yaraví S.A.C.",
            ruc="20123456789",
            direccion="Av. Ejército 710, Yanahuara, Arequipa",
            sector="Medios de comunicación",
            telefono="054-254321",
            email="contacto@radioyaravi.pe",
            created_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
        )
    )
    db.flush()  # FK para supervisor y práctica
    db.add(
        Supervisor(
            id="s-1",
            empresa_id="e-1",
            nombres="Marisol",
            apellidos="Chávez",
            cargo="Jefa de Prensa",
            email="m.chavez@radioyaravi.pe",
            telefono="954-112233",
        )
    )

    # ── Prácticas (HU-14/15/18) ────────────────────────────────────────────────
    db.add_all(
        [
            Practica(
                id="pr-1",
                practicante_id="u-alumno",
                aula_id="a-1",
                periodo="2026-I",
                empresa_id="e-1",
                horas_acumuladas=148,
                horas_minimas=360,
                estado=PracticaEstadoEnum.EN_CURSO,
                fecha_inicio=datetime(2026, 4, 1, tzinfo=timezone.utc),
            ),
            Practica(
                id="pr-0",
                practicante_id="u-alumno",
                aula_id="a-2",
                periodo="2025-II",
                empresa_id=None,
                horas_acumuladas=360,
                horas_minimas=360,
                estado=PracticaEstadoEnum.CERRADA,
                fecha_inicio=datetime(2025, 8, 15, tzinfo=timezone.utc),
                fecha_cierre=datetime(2025, 12, 10, tzinfo=timezone.utc),
                validado_por="Jose Luis Cuenca",
            ),
        ]
    )
    db.flush()  # FK para registros de horas

    # ── Bitácora de horas de la práctica activa (HU-14) ────────────────────────
    db.add_all(
        [
            RegistroHoras(
                id="h-1",
                practica_id="pr-1",
                fecha=datetime(2026, 5, 2, tzinfo=timezone.utc),
                horas=40,
                descripcion="Producción de notas informativas semanales.",
            ),
            RegistroHoras(
                id="h-2",
                practica_id="pr-1",
                fecha=datetime(2026, 6, 1, tzinfo=timezone.utc),
                horas=60,
                descripcion="Edición de contenidos para redes sociales.",
            ),
            RegistroHoras(
                id="h-3",
                practica_id="pr-1",
                fecha=datetime(2026, 6, 25, tzinfo=timezone.utc),
                horas=48,
                descripcion="Cobertura de eventos institucionales.",
            ),
        ]
    )
    print("[OK] Prácticas, empresa y horas insertadas.")


def _seed_notificaciones(db) -> None:
    """Notificaciones de tareas y vencimientos (HU-17)."""
    if db.query(Notificacion).count() > 0:
        return

    ahora = datetime.now(timezone.utc)
    db.add_all(
        [
            Notificacion(
                id="n-1",
                user_id="u-alumno",
                tipo=NotificacionTipoEnum.TAREA_ASIGNADA,
                titulo="Nueva tarea asignada",
                mensaje="Se te asignó: Entrega de informe mensual.",
                leida=0,
                fecha=ahora - timedelta(days=2),
            ),
            Notificacion(
                id="n-2",
                user_id="u-alumno",
                tipo=NotificacionTipoEnum.VENCIMIENTO,
                titulo="Vencimiento próximo",
                mensaje='"Entrega de informe mensual" vence en 3 días.',
                leida=0,
                fecha=ahora,
            ),
        ]
    )
    print("[OK] Notificaciones insertadas.")


def seed():
    # Crea tablas si no existen (alternativa a Alembic para desarrollo rápido)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _seed_base(db)
        _seed_practicas(db)
        _seed_notificaciones(db)
        db.commit()
        print("[OK] Semilla verificada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
