"""
Vistas del profesor/asesor (HU-11): progreso de practicantes.
Panel de control del profesor (HU-22): alumnos activos, entregas pendientes,
asistencia promedio y alumnos en riesgo.
Rutas: /api/v1/profesor/*
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    Aula,
    Empresa,
    Entrega,
    EntregaEstadoEnum,
    Inscripcion,
    Meta,
    MetaTipoEnum,
    Practica,
    PracticaEstadoEnum,
    RegistroAsistencia,
    Tarea,
    User,
)
from app.schemas.schemas import (
    AlumnoEnRiesgoOut,
    AsistenciaItemOut,
    AsistenciaSesionOut,
    CalificarEntregaRequest,
    EntregaProfesorOut,
    GuardarAsistenciaRequest,
    LibroAlumnoOut,
    LibroCalificacionesOut,
    LibroTareaOut,
    PracticanteProgresoOut,
    ResumenProfesorOut,
    SeguimientoEntregaOut,
    SeguimientoOut,
)

router = APIRouter(prefix="/profesor", tags=["profesor"])

# Duración típica de un ciclo de prácticas (días), usada para estimar el ritmo
# esperado de horas. Supuesto ajustable, documentado explícitamente.
DURACION_ESPERADA_DIAS = 180
# Avance de meta por debajo de este umbral se considera riesgo.
META_RIESGO_UMBRAL = 0.3


def _solo_profesor_o_admin(user: User) -> None:
    if user.role.value not in ("PROFESOR", "ADMIN"):
        raise HTTPException(status_code=403, detail="Acceso restringido.")


def _as_utc(dt: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes naive; los normaliza a UTC para poder comparar."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── GET /api/v1/profesor/practicantes ─────────────────────────────────────────


@router.get("/practicantes", response_model=list[PracticanteProgresoOut])
def list_practicantes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista todos los practicantes inscritos en las aulas del profesor,
    con su avance, semanas y estado de entrega de tareas.
    El rol ADMIN ve todas las aulas.
    """
    _solo_profesor_o_admin(current_user)

    if current_user.role.value == "ADMIN":
        aulas = db.query(Aula).all()
    else:
        aulas = db.query(Aula).filter(Aula.profesor_id == current_user.id).all()

    aula_map = {a.id: a for a in aulas}
    aula_ids = list(aula_map.keys())

    inscripciones = (
        db.query(Inscripcion)
        .filter(Inscripcion.aula_id.in_(aula_ids))
        .all()
    )

    resultado: list[PracticanteProgresoOut] = []
    for ins in inscripciones:
        aula = aula_map[ins.aula_id]
        alumno: User = ins.alumno

        tareas = db.query(Tarea).filter(Tarea.aula_id == ins.aula_id).all()
        tareas_total = len(tareas)
        tareas_entregadas = 0
        if tareas_total > 0:
            tareas_entregadas = (
                db.query(Entrega)
                .filter(
                    Entrega.alumno_id == ins.alumno_id,
                    Entrega.tarea_id.in_([t.id for t in tareas]),
                )
                .count()
            )

        resultado.append(
            PracticanteProgresoOut(
                alumnoId=alumno.id,
                alumnoNombre=f"{alumno.nombres} {alumno.apellidos}",
                alumnoEmail=alumno.email,
                aulaId=aula.id,
                aulaNombre=aula.nombre,
                progreso=ins.progreso,
                semanaActual=ins.semana_actual,
                semanasTotales=ins.semanas_totales,
                estado=aula.estado.value,
                tareasEntregadas=tareas_entregadas,
                tareasTotal=tareas_total,
            )
        )

    resultado.sort(key=lambda x: (x.aulaNombre, x.alumnoNombre))
    return resultado


def _tareas_vencidas_sin_entregar(
    tareas_aula: list[Tarea], entregadas_ids: set[str], ahora: datetime
) -> int:
    vencidas = [t for t in tareas_aula if t.fecha_limite and _as_utc(t.fecha_limite) < ahora]
    return len([t for t in vencidas if t.id not in entregadas_ids])


def _evaluar_riesgo(
    practica: Practica,
    tareas_por_aula: dict[str, list[Tarea]],
    entregas_por_alumno: dict[str, set[str]],
    metas_por_practica: dict[str, list[Meta]],
    ahora: datetime,
) -> list[str]:
    motivos: list[str] = []

    tareas_aula = tareas_por_aula.get(practica.aula_id, [])
    entregadas = entregas_por_alumno.get(practica.practicante_id, set())
    n_vencidas = _tareas_vencidas_sin_entregar(tareas_aula, entregadas, ahora)
    if n_vencidas > 0:
        motivos.append(f"{n_vencidas} tarea(s) vencida(s)")

    inicio = _as_utc(practica.fecha_inicio)
    dias_transcurridos = (ahora - inicio).days if inicio else 0
    progreso_esperado = min(1, dias_transcurridos / DURACION_ESPERADA_DIAS)
    progreso_real = (
        practica.horas_acumuladas / practica.horas_minimas if practica.horas_minimas else 0
    )
    if progreso_esperado > 0.3 and progreso_real < progreso_esperado * 0.6:
        motivos.append("Atrasado en horas acumuladas")

    metas_bajas = 0
    for m in metas_por_practica.get(practica.id, []):
        alcanzada = (
            practica.horas_acumuladas if m.tipo == MetaTipoEnum.HORAS else m.cantidad_alcanzada
        )
        if m.cantidad_objetivo and alcanzada / m.cantidad_objetivo < META_RIESGO_UMBRAL:
            metas_bajas += 1
    if metas_bajas > 0:
        motivos.append(f"{metas_bajas} meta(s) con avance bajo")

    return motivos


# ── GET /api/v1/profesor/resumen ──────────────────────────────────────────────


@router.get("/resumen", response_model=ResumenProfesorOut)
def resumen_profesor(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Panel de control del profesor (HU-22)."""
    _solo_profesor_o_admin(current_user)

    if current_user.role.value == "ADMIN":
        aulas = db.query(Aula).all()
    else:
        aulas = db.query(Aula).filter(Aula.profesor_id == current_user.id).all()
    aula_ids = [a.id for a in aulas]

    practicas = (
        db.query(Practica).filter(Practica.aula_id.in_(aula_ids)).all() if aula_ids else []
    )
    activas = [p for p in practicas if p.estado != PracticaEstadoEnum.CERRADA]
    alumnos_activos = len({p.practicante_id for p in activas})

    inscripciones = (
        db.query(Inscripcion).filter(Inscripcion.aula_id.in_(aula_ids)).all()
        if aula_ids
        else []
    )
    tareas = db.query(Tarea).filter(Tarea.aula_id.in_(aula_ids)).all() if aula_ids else []
    tareas_por_aula: dict[str, list[Tarea]] = {}
    for t in tareas:
        tareas_por_aula.setdefault(t.aula_id, []).append(t)

    tarea_ids = [t.id for t in tareas]
    entregas_por_alumno: dict[str, set[str]] = {}
    if tarea_ids:
        for e in db.query(Entrega).filter(Entrega.tarea_id.in_(tarea_ids)):
            entregas_por_alumno.setdefault(e.alumno_id, set()).add(e.tarea_id)

    ahora = datetime.now(timezone.utc)
    entregas_pendientes = 0
    for ins in inscripciones:
        tareas_aula = tareas_por_aula.get(ins.aula_id, [])
        entregadas = entregas_por_alumno.get(ins.alumno_id, set())
        entregas_pendientes += len([t for t in tareas_aula if t.id not in entregadas])

    asistencias = (
        db.query(RegistroAsistencia).filter(RegistroAsistencia.aula_id.in_(aula_ids)).all()
        if aula_ids
        else []
    )
    asistencia_promedio = None
    if asistencias:
        presentes = len([a for a in asistencias if a.presente])
        asistencia_promedio = round(presentes / len(asistencias) * 100)

    practica_ids = [p.id for p in practicas]
    metas_por_practica: dict[str, list[Meta]] = {}
    if practica_ids:
        for m in db.query(Meta).filter(Meta.practica_id.in_(practica_ids)):
            metas_por_practica.setdefault(m.practica_id, []).append(m)

    en_riesgo: list[AlumnoEnRiesgoOut] = []
    for p in activas:
        motivos = _evaluar_riesgo(p, tareas_por_aula, entregas_por_alumno, metas_por_practica, ahora)
        if motivos:
            en_riesgo.append(
                AlumnoEnRiesgoOut(
                    practicanteId=p.practicante_id,
                    practicanteNombre=f"{p.practicante.nombres} {p.practicante.apellidos}",
                    motivos=motivos,
                )
            )

    return ResumenProfesorOut(
        alumnosActivos=alumnos_activos,
        entregasPendientes=entregas_pendientes,
        asistenciaPromedio=asistencia_promedio,
        alumnosEnRiesgo=en_riesgo,
    )


# ── Helpers de docencia (HU-25/26/27/28) ──────────────────────────────────────


def _aula_del_profesor(aula_id: str, user: User, db: Session) -> Aula:
    """Devuelve el aula si el profesor la dicta (o si es admin); si no, 403/404."""
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if aula is None:
        raise HTTPException(status_code=404, detail="Aula no encontrada.")
    if user.role.value != "ADMIN" and aula.profesor_id != user.id:
        raise HTTPException(status_code=403, detail="Esta aula no te pertenece.")
    return aula


def _alumnos_de_aula(aula_id: str, db: Session) -> list[User]:
    inscripciones = (
        db.query(Inscripcion).filter(Inscripcion.aula_id == aula_id).all()
    )
    alumnos = [ins.alumno for ins in inscripciones]
    alumnos.sort(key=lambda a: (a.apellidos, a.nombres))
    return alumnos


def _rango_dia(fecha_str: str) -> tuple[datetime, datetime]:
    """Convierte 'YYYY-MM-DD' en el rango [00:00, +1 día) en UTC."""
    try:
        base = datetime.strptime(fecha_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="Fecha inválida (usa YYYY-MM-DD).")
    return base, base + timedelta(days=1)


# ── HU-25 · Registro de asistencia ────────────────────────────────────────────


@router.get("/aulas/{aula_id}/asistencia", response_model=AsistenciaSesionOut)
def get_asistencia(
    aula_id: str,
    fecha: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Estado de asistencia del aula en una fecha (por defecto todos presentes)."""
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)

    desde, hasta = _rango_dia(fecha)
    registros = (
        db.query(RegistroAsistencia)
        .filter(
            RegistroAsistencia.aula_id == aula_id,
            RegistroAsistencia.fecha >= desde,
            RegistroAsistencia.fecha < hasta,
        )
        .all()
    )
    presente_por_alumno = {r.practicante_id: bool(r.presente) for r in registros}

    items = [
        AsistenciaItemOut(
            practicanteId=a.id,
            practicanteNombre=f"{a.nombres} {a.apellidos}",
            # Si aún no hay registro para ese día, se asume presente por defecto.
            presente=presente_por_alumno.get(a.id, True),
        )
        for a in _alumnos_de_aula(aula_id, db)
    ]
    return AsistenciaSesionOut(aulaId=aula_id, fecha=fecha[:10], items=items)


@router.post("/aulas/{aula_id}/asistencia", response_model=AsistenciaSesionOut)
def guardar_asistencia(
    aula_id: str,
    payload: GuardarAsistenciaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guarda (reemplaza) la asistencia del aula para una fecha."""
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)

    desde, hasta = _rango_dia(payload.fecha)
    # Reemplaza los registros existentes de ese día para no duplicar.
    db.query(RegistroAsistencia).filter(
        RegistroAsistencia.aula_id == aula_id,
        RegistroAsistencia.fecha >= desde,
        RegistroAsistencia.fecha < hasta,
    ).delete(synchronize_session=False)

    for item in payload.items:
        db.add(
            RegistroAsistencia(
                practicante_id=item.practicanteId,
                aula_id=aula_id,
                fecha=desde,
                presente=1 if item.presente else 0,
            )
        )
    db.commit()
    return get_asistencia(aula_id, payload.fecha, db, current_user)


# ── HU-26 · Revisar y calificar entregas ──────────────────────────────────────


def _entrega_prof_out(e: Entrega) -> EntregaProfesorOut:
    return EntregaProfesorOut(
        id=e.id,
        tareaId=e.tarea_id,
        tareaTitulo=e.tarea.titulo if e.tarea else "",
        alumnoId=e.alumno_id,
        alumnoNombre=f"{e.alumno.nombres} {e.alumno.apellidos}" if e.alumno else "",
        descripcion=e.descripcion,
        comentario=e.comentario,
        archivoId=e.archivo_id,
        estado=e.estado.value,
        nota=e.nota,
        retroalimentacion=e.retroalimentacion,
        createdAt=e.created_at.isoformat() if e.created_at else "",
    )


@router.get("/aulas/{aula_id}/entregas", response_model=list[EntregaProfesorOut])
def list_entregas_aula(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todas las entregas de las tareas del aula, para revisión del profesor."""
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)

    tareas = db.query(Tarea).filter(Tarea.aula_id == aula_id).all()
    tarea_ids = [t.id for t in tareas]
    if not tarea_ids:
        return []

    entregas = (
        db.query(Entrega)
        .filter(Entrega.tarea_id.in_(tarea_ids))
        .order_by(Entrega.estado.asc(), Entrega.created_at.desc())
        .all()
    )
    return [_entrega_prof_out(e) for e in entregas]


@router.put("/entregas/{entrega_id}/calificar", response_model=EntregaProfesorOut)
def calificar_entrega(
    entrega_id: str,
    payload: CalificarEntregaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Asigna nota (0–20) y retroalimentación a una entrega."""
    _solo_profesor_o_admin(current_user)

    entrega = db.query(Entrega).filter(Entrega.id == entrega_id).first()
    if entrega is None:
        raise HTTPException(status_code=404, detail="Entrega no encontrada.")

    tarea = db.query(Tarea).filter(Tarea.id == entrega.tarea_id).first()
    if tarea is not None:
        _aula_del_profesor(tarea.aula_id, current_user, db)

    entrega.nota = payload.nota
    entrega.retroalimentacion = payload.retroalimentacion
    entrega.estado = EntregaEstadoEnum.CALIFICADA
    db.commit()
    db.refresh(entrega)
    return _entrega_prof_out(entrega)


# ── HU-27 · Libro de calificaciones ───────────────────────────────────────────


@router.get("/aulas/{aula_id}/libro", response_model=LibroCalificacionesOut)
def libro_calificaciones(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Libro de notas consolidado del aula: notas por tarea, asistencia y horas."""
    _solo_profesor_o_admin(current_user)
    aula = _aula_del_profesor(aula_id, current_user, db)

    tareas = (
        db.query(Tarea).filter(Tarea.aula_id == aula_id).order_by(Tarea.created_at.asc()).all()
    )
    tarea_ids = [t.id for t in tareas]
    alumnos = _alumnos_de_aula(aula_id, db)

    # Entregas por (alumno, tarea)
    notas_por_alumno: dict[str, dict[str, int | None]] = {}
    if tarea_ids:
        for e in db.query(Entrega).filter(Entrega.tarea_id.in_(tarea_ids)).all():
            notas_por_alumno.setdefault(e.alumno_id, {})[e.tarea_id] = e.nota

    # Asistencia por alumno
    asistencias = db.query(RegistroAsistencia).filter(RegistroAsistencia.aula_id == aula_id).all()
    asist_por_alumno: dict[str, list[int]] = {}
    for r in asistencias:
        asist_por_alumno.setdefault(r.practicante_id, []).append(1 if r.presente else 0)

    # Horas por alumno (práctica en esta aula)
    horas_por_alumno: dict[str, int] = {}
    for p in db.query(Practica).filter(Practica.aula_id == aula_id).all():
        horas_por_alumno[p.practicante_id] = p.horas_acumuladas

    filas: list[LibroAlumnoOut] = []
    promedios_validos: list[float] = []
    for a in alumnos:
        notas_map = notas_por_alumno.get(a.id, {})
        notas_out = {t.id: notas_map.get(t.id) for t in tareas}
        vals = [n for n in notas_map.values() if n is not None]
        promedio = round(sum(vals) / len(vals), 2) if vals else None
        if promedio is not None:
            promedios_validos.append(promedio)

        dias = asist_por_alumno.get(a.id, [])
        asistencia_pct = round(sum(dias) / len(dias) * 100) if dias else None

        filas.append(
            LibroAlumnoOut(
                alumnoId=a.id,
                alumnoNombre=f"{a.nombres} {a.apellidos}",
                codigo=a.id,
                notas=notas_out,
                promedio=promedio,
                asistenciaPct=asistencia_pct,
                horas=horas_por_alumno.get(a.id, 0),
            )
        )

    promedio_general = (
        round(sum(promedios_validos) / len(promedios_validos), 2)
        if promedios_validos
        else None
    )

    return LibroCalificacionesOut(
        aulaId=aula.id,
        aulaNombre=aula.nombre,
        tareas=[LibroTareaOut(id=t.id, titulo=t.titulo) for t in tareas],
        alumnos=filas,
        promedioGeneral=promedio_general,
    )


# ── HU-28 · Seguimiento individual del practicante ────────────────────────────


@router.get(
    "/aulas/{aula_id}/practicantes/{alumno_id}/seguimiento",
    response_model=SeguimientoOut,
)
def seguimiento_practicante(
    aula_id: str,
    alumno_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ficha de seguimiento de un practicante en un aula."""
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)

    alumno = db.query(User).filter(User.id == alumno_id).first()
    if alumno is None:
        raise HTTPException(status_code=404, detail="Practicante no encontrado.")

    ins = (
        db.query(Inscripcion)
        .filter(Inscripcion.aula_id == aula_id, Inscripcion.alumno_id == alumno_id)
        .first()
    )

    tareas = db.query(Tarea).filter(Tarea.aula_id == aula_id).order_by(Tarea.created_at.asc()).all()
    entregas_map: dict[str, Entrega] = {}
    if tareas:
        for e in (
            db.query(Entrega)
            .filter(
                Entrega.alumno_id == alumno_id,
                Entrega.tarea_id.in_([t.id for t in tareas]),
            )
            .all()
        ):
            entregas_map[e.tarea_id] = e

    entregas_out: list[SeguimientoEntregaOut] = []
    notas: list[int] = []
    for t in tareas:
        e = entregas_map.get(t.id)
        if e and e.nota is not None:
            notas.append(e.nota)
        entregas_out.append(
            SeguimientoEntregaOut(
                tareaTitulo=t.titulo,
                nota=e.nota if e else None,
                estado=e.estado.value if e else "PENDIENTE",
                retroalimentacion=e.retroalimentacion if e else None,
            )
        )
    promedio = round(sum(notas) / len(notas), 2) if notas else None

    dias = [
        1 if r.presente else 0
        for r in db.query(RegistroAsistencia)
        .filter(
            RegistroAsistencia.aula_id == aula_id,
            RegistroAsistencia.practicante_id == alumno_id,
        )
        .all()
    ]
    asistencia_pct = round(sum(dias) / len(dias) * 100) if dias else None

    practica = (
        db.query(Practica)
        .filter(Practica.aula_id == aula_id, Practica.practicante_id == alumno_id)
        .first()
    )
    empresa_nombre = None
    if practica and practica.empresa_id:
        emp = db.query(Empresa).filter(Empresa.id == practica.empresa_id).first()
        empresa_nombre = emp.razon_social if emp else None

    # Reutiliza el evaluador de riesgo del panel del profesor.
    motivos: list[str] = []
    if practica and practica.estado != PracticaEstadoEnum.CERRADA:
        tareas_por_aula = {aula_id: tareas}
        entregadas = {alumno_id: set(entregas_map.keys())}
        metas_por_practica: dict[str, list[Meta]] = {}
        for m in db.query(Meta).filter(Meta.practica_id == practica.id):
            metas_por_practica.setdefault(m.practica_id, []).append(m)
        motivos = _evaluar_riesgo(
            practica, tareas_por_aula, entregadas, metas_por_practica,
            datetime.now(timezone.utc),
        )

    return SeguimientoOut(
        practicanteId=alumno.id,
        practicanteNombre=f"{alumno.nombres} {alumno.apellidos}",
        practicanteEmail=alumno.email,
        aulaId=aula_id,
        aulaNombre=_aula_del_profesor(aula_id, current_user, db).nombre,
        empresaNombre=empresa_nombre,
        promedio=promedio,
        asistenciaPct=asistencia_pct,
        horasAcumuladas=practica.horas_acumuladas if practica else 0,
        horasMinimas=practica.horas_minimas if practica else 360,
        progreso=ins.progreso if ins else 0,
        estadoPractica=practica.estado.value if practica else None,
        entregas=entregas_out,
        motivosRiesgo=motivos,
    )
