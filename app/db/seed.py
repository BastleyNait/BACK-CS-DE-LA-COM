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
    Anuncio,
    Aula,
    AulaEstadoEnum,
    Base,
    Empresa,
    ForoHilo,
    ForoMensaje,
    MensajeDirecto,
    Entrega,
    EntregaEstadoEnum,
    Evaluacion,
    EvaluacionEstadoEnum,
    Inscripcion,
    Meta,
    MetaTipoEnum,
    Notificacion,
    NotificacionTipoEnum,
    Practica,
    PracticaEstadoEnum,
    RegistroAsistencia,
    RegistroHoras,
    RegistroHorasEstadoEnum,
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
    supervisor_user = User(
        id="u-supervisor",
        nombres="Marisol",
        apellidos="Chávez",
        email="supervisor@radioyaravi.pe",
        hashed_password=hash_password("supervisor123"),
        role=RoleEnum.SUPERVISOR,
    )
    db.add_all([admin, profesor, alumno, supervisor_user])
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
            user_id="u-supervisor",
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
                estado_validacion=RegistroHorasEstadoEnum.VALIDADO,
            ),
            RegistroHoras(
                id="h-2",
                practica_id="pr-1",
                fecha=datetime(2026, 6, 1, tzinfo=timezone.utc),
                horas=60,
                descripcion="Edición de contenidos para redes sociales.",
                estado_validacion=RegistroHorasEstadoEnum.VALIDADO,
            ),
            RegistroHoras(
                id="h-3",
                practica_id="pr-1",
                fecha=datetime(2026, 6, 25, tzinfo=timezone.utc),
                horas=48,
                descripcion="Cobertura de eventos institucionales.",
                estado_validacion=RegistroHorasEstadoEnum.PENDIENTE,
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


def _seed_metas_y_seguimiento(db) -> None:
    """Metas, asistencia y evaluaciones (HU-20/21/22/24)."""
    if db.query(Meta).count() > 0:
        return

    db.add_all(
        [
            Meta(
                id="m-1",
                practica_id="pr-1",
                tipo=MetaTipoEnum.NOTAS_PERIODISTICAS,
                cantidad_objetivo=10,
                cantidad_alcanzada=4,
                descripcion="Notas informativas para el boletín semanal.",
                creado_por="Jose Luis Cuenca",
                created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            ),
            Meta(
                id="m-2",
                practica_id="pr-1",
                tipo=MetaTipoEnum.HORAS,
                cantidad_objetivo=360,
                cantidad_alcanzada=148,
                descripcion="Cumplimiento del mínimo reglamentario de horas.",
                creado_por="Jose Luis Cuenca",
                created_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
            ),
        ]
    )

    db.add_all(
        [
            RegistroAsistencia(
                id="as-1",
                practicante_id="u-alumno",
                aula_id="a-1",
                fecha=datetime(2026, 5, 4, tzinfo=timezone.utc),
                presente=1,
            ),
            RegistroAsistencia(
                id="as-2",
                practicante_id="u-alumno",
                aula_id="a-1",
                fecha=datetime(2026, 5, 11, tzinfo=timezone.utc),
                presente=1,
            ),
            RegistroAsistencia(
                id="as-3",
                practicante_id="u-alumno",
                aula_id="a-1",
                fecha=datetime(2026, 5, 18, tzinfo=timezone.utc),
                presente=0,
            ),
            RegistroAsistencia(
                id="as-4",
                practicante_id="u-alumno",
                aula_id="a-1",
                fecha=datetime(2026, 5, 25, tzinfo=timezone.utc),
                presente=1,
            ),
        ]
    )

    db.add_all(
        [
            Evaluacion(
                id="ev-1",
                practica_id="pr-1",
                empresa_id="e-1",
                periodo="2026-I",
                estado=EvaluacionEstadoEnum.PENDIENTE,
                fecha_limite=datetime(2026, 7, 20, tzinfo=timezone.utc),
            ),
            Evaluacion(
                id="ev-0",
                practica_id="pr-0",
                empresa_id="e-1",
                periodo="2025-II",
                estado=EvaluacionEstadoEnum.COMPLETADA,
                fecha_limite=datetime(2025, 12, 15, tzinfo=timezone.utc),
            ),
        ]
    )
    print("[OK] Metas, asistencia y evaluaciones insertadas.")


def _seed_docencia(db) -> None:
    """
    Practicantes adicionales del aula a-1 con entregas y asistencia, para que las
    vistas de docencia del profesor (asistencia, libro de notas, seguimiento —
    HU-25/26/27/28) tengan datos representativos.
    """
    if db.query(User).filter(User.id == "u-alumno2").first():
        return

    maria = User(
        id="u-alumno2",
        nombres="María",
        apellidos="Quispe Mamani",
        email="maria.quispe@unsa.edu.pe",
        hashed_password=hash_password("alumno123"),
        role=RoleEnum.ALUMNO,
    )
    andres = User(
        id="u-alumno3",
        nombres="Andrés",
        apellidos="Coyla Choque",
        email="andres.coyla@unsa.edu.pe",
        hashed_password=hash_password("alumno123"),
        role=RoleEnum.ALUMNO,
    )
    db.add_all([maria, andres])
    db.flush()

    db.add_all(
        [
            Inscripcion(alumno_id="u-alumno2", aula_id="a-1", progreso=48, semana_actual=9, semanas_totales=16),
            Inscripcion(alumno_id="u-alumno3", aula_id="a-1", progreso=82, semana_actual=9, semanas_totales=16),
        ]
    )

    db.add_all(
        [
            Practica(
                id="pr-2", practicante_id="u-alumno2", aula_id="a-1", periodo="2026-I",
                horas_acumuladas=95, horas_minimas=360, estado=PracticaEstadoEnum.EN_CURSO,
                fecha_inicio=datetime(2026, 4, 1, tzinfo=timezone.utc),
            ),
            Practica(
                id="pr-3", practicante_id="u-alumno3", aula_id="a-1", periodo="2026-I",
                horas_acumuladas=240, horas_minimas=360, estado=PracticaEstadoEnum.EN_CURSO,
                fecha_inicio=datetime(2026, 4, 1, tzinfo=timezone.utc),
            ),
        ]
    )

    # Entregas: algunas calificadas, otras pendientes de revisión (HU-26).
    db.add_all(
        [
            # u-alumno: entrega pendiente en t-2 (además de ent-1 ya calificada)
            Entrega(id="ent-2", tarea_id="t-2", alumno_id="u-alumno",
                    descripcion="Informe de la semana 9 con evidencias fotográficas.",
                    comentario="Adjunto cobertura del evento institucional.",
                    estado=EntregaEstadoEnum.ENTREGADA, nota=None,
                    created_at=datetime(2026, 5, 16, tzinfo=timezone.utc)),
            # María: t-1 calificada, t-2 pendiente
            Entrega(id="ent-3", tarea_id="t-1", alumno_id="u-alumno2",
                    descripcion="Informe semana 8.", comentario="Trabajé en redacción de notas.",
                    estado=EntregaEstadoEnum.CALIFICADA, nota=14,
                    retroalimentacion="Buen avance, cuida la ortografía.",
                    created_at=datetime(2026, 5, 9, tzinfo=timezone.utc)),
            Entrega(id="ent-4", tarea_id="t-2", alumno_id="u-alumno2",
                    descripcion="Informe semana 9.", comentario="",
                    estado=EntregaEstadoEnum.ENTREGADA, nota=None,
                    created_at=datetime(2026, 5, 17, tzinfo=timezone.utc)),
            # Andrés: t-1 y t-2 calificadas
            Entrega(id="ent-5", tarea_id="t-1", alumno_id="u-alumno3",
                    descripcion="Informe semana 8.", comentario="Cobertura radial.",
                    estado=EntregaEstadoEnum.CALIFICADA, nota=18,
                    retroalimentacion="Excelente trabajo de campo.",
                    created_at=datetime(2026, 5, 8, tzinfo=timezone.utc)),
            Entrega(id="ent-6", tarea_id="t-2", alumno_id="u-alumno3",
                    descripcion="Informe semana 9.", comentario="",
                    estado=EntregaEstadoEnum.CALIFICADA, nota=16,
                    retroalimentacion="Muy completo.",
                    created_at=datetime(2026, 5, 16, tzinfo=timezone.utc)),
        ]
    )

    # Asistencia de los 3 practicantes en varias sesiones (HU-25).
    fechas = [datetime(2026, 5, d, tzinfo=timezone.utc) for d in (4, 11, 18, 25)]
    presencias = {
        "u-alumno2": [1, 0, 1, 1],
        "u-alumno3": [1, 1, 1, 1],
    }
    for aid, pres in presencias.items():
        for f, p in zip(fechas, pres):
            db.add(RegistroAsistencia(practicante_id=aid, aula_id="a-1", fecha=f, presente=p))

    print("[OK] Docencia (practicantes, entregas y asistencia) insertada.")


def _seed_comunicacion(db) -> None:
    """Anuncios, foro y mensajería del aula a-1 (HU-36/37/38)."""
    if db.query(Anuncio).count() > 0:
        return

    prof = "Jose Luis Cuenca"
    db.add_all(
        [
            Anuncio(
                id="an-1", aula_id="a-1", autor_id="u-prof", autor_nombre=prof,
                titulo="Rúbrica del Informe N.° 9 disponible",
                mensaje="Ya pueden descargar la rúbrica del informe semanal N.° 9 en Materiales.",
                fijado=1, created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            ),
            Anuncio(
                id="an-2", aula_id="a-1", autor_id="u-prof", autor_nombre=prof,
                titulo="Cambio de horario de la sesión del miércoles",
                mensaje="La sesión del miércoles se adelanta a las 4:00 pm por disponibilidad del aula.",
                fijado=0, created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            ),
        ]
    )

    hilo = ForoHilo(
        id="fh-1", aula_id="a-1", autor_id="u-prof", autor_nombre=prof,
        titulo="Semana 9 — Debate: ética en el periodismo digital",
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    db.add(hilo)
    db.flush()
    db.add_all(
        [
            ForoMensaje(
                hilo_id="fh-1", autor_id="u-prof", autor_nombre=prof,
                texto="Abramos el debate: ¿hasta dónde llega la responsabilidad del periodista frente a la desinformación?",
                created_at=datetime(2026, 5, 21, 10, tzinfo=timezone.utc),
            ),
            ForoMensaje(
                hilo_id="fh-1", autor_id="u-alumno3", autor_nombre="Andrés Coyla Choque",
                texto="Creo que la verificación de fuentes es el mínimo ético indispensable.",
                created_at=datetime(2026, 5, 21, 12, tzinfo=timezone.utc),
            ),
        ]
    )

    db.add_all(
        [
            MensajeDirecto(
                aula_id="a-1", remitente_id="u-alumno", destinatario_id="u-prof",
                texto="Profesor, ¿puedo entregar el informe el sábado? Tengo cobertura el viernes.",
                leido=1, created_at=datetime(2026, 5, 22, 9, tzinfo=timezone.utc),
            ),
            MensajeDirecto(
                aula_id="a-1", remitente_id="u-prof", destinatario_id="u-alumno",
                texto="Sí, te apruebo hasta el sábado 10 am. Adjunta la justificación de la cobertura.",
                leido=1, created_at=datetime(2026, 5, 22, 11, tzinfo=timezone.utc),
            ),
            MensajeDirecto(
                aula_id="a-1", remitente_id="u-alumno2", destinatario_id="u-prof",
                texto="Buenas, tengo una duda sobre el formato de citas APA.",
                leido=0, created_at=datetime(2026, 5, 23, 8, tzinfo=timezone.utc),
            ),
        ]
    )
    print("[OK] Comunicacion (anuncios, foro y mensajes) insertada.")


def seed():
    # Crea tablas si no existen (alternativa a Alembic para desarrollo rápido)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        _seed_base(db)
        _seed_practicas(db)
        _seed_notificaciones(db)
        _seed_metas_y_seguimiento(db)
        _seed_docencia(db)
        _seed_comunicacion(db)
        db.commit()
        print("[OK] Semilla verificada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
