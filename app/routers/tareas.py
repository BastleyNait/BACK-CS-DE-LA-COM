"""
Tareas y entregas del alumno (HU-09 entrega / HU-10 calificaciones).
Rutas: /api/v1/alumno/aulas/{aula_id}/tareas/*
       /api/v1/alumno/aulas/{aula_id}/calificaciones
"""

from datetime import datetime, timezone
from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    Archivo,
    Aula,
    AulaEstadoEnum,
    Entrega,
    EntregaEstadoEnum,
    Inscripcion,
    Practica,
    PracticaEstadoEnum,
    Tarea,
    User,
)
from app.schemas.schemas import (
    CalificacionesOut,
    CreateTareaRequest,
    DetalleCalificacionOut,
    EntregaOut,
    SubmitEntregaRequest,
    TareaAlumnoOut,
)

router = APIRouter(tags=["tareas"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _solo_alumno(user: User) -> None:
    if user.role.value != "ALUMNO":
        raise HTTPException(status_code=403, detail="Solo los alumnos pueden acceder.")


def _verificar_inscripcion(aula_id: str, alumno_id: str, db: Session) -> None:
    ins = (
        db.query(Inscripcion)
        .filter(
            Inscripcion.alumno_id == alumno_id,
            Inscripcion.aula_id == aula_id,
        )
        .first()
    )
    if ins is None:
        raise HTTPException(status_code=403, detail="No estás inscrito en esta aula.")


def _entrega_to_out(e: Entrega) -> EntregaOut:
    return EntregaOut(
        id=e.id,
        tareaId=e.tarea_id,
        alumnoId=e.alumno_id,
        descripcion=e.descripcion,
        comentario=e.comentario,
        archivoId=e.archivo_id,
        estado=e.estado.value,
        nota=e.nota,
        retroalimentacion=e.retroalimentacion,
        createdAt=e.created_at.isoformat() if e.created_at else "",
    )


def _tarea_to_out(t: Tarea, entrega: Entrega | None) -> TareaAlumnoOut:
    return TareaAlumnoOut(
        id=t.id,
        aulaId=t.aula_id,
        titulo=t.titulo,
        descripcion=t.descripcion,
        fechaLimite=t.fecha_limite.isoformat() if t.fecha_limite else None,
        createdAt=t.created_at.isoformat() if t.created_at else "",
        entrega=_entrega_to_out(entrega) if entrega else None,
    )


# ── GET /api/v1/alumno/aulas/{aula_id}/tareas ────────────────────────────────


@router.get("/alumno/aulas/{aula_id}/tareas", response_model=list[TareaAlumnoOut])
def list_tareas(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista las tareas del aula con el estado de entrega del alumno."""
    _solo_alumno(current_user)
    _verificar_inscripcion(aula_id, current_user.id, db)

    tareas = (
        db.query(Tarea)
        .filter(Tarea.aula_id == aula_id)
        .order_by(Tarea.fecha_limite.asc())
        .all()
    )

    resultado = []
    for t in tareas:
        entrega = (
            db.query(Entrega)
            .filter(Entrega.tarea_id == t.id, Entrega.alumno_id == current_user.id)
            .first()
        )
        resultado.append(_tarea_to_out(t, entrega))
    return resultado


# ── POST /api/v1/alumno/aulas/{aula_id}/tareas/{tarea_id}/entregas ───────────


@router.post(
    "/alumno/aulas/{aula_id}/tareas/{tarea_id}/entregas",
    response_model=TareaAlumnoOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_entrega(
    aula_id: str,
    tarea_id: str,
    payload: SubmitEntregaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envía la entrega de un alumno para una tarea. Permite una sola entrega."""
    _solo_alumno(current_user)
    _verificar_inscripcion(aula_id, current_user.id, db)

    # Todas las entregas de una tarea se serializan antes de comprobar duplicados.
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.aula_id == aula_id).populate_existing().with_for_update().first()
    if tarea is None:
        raise HTTPException(404, "Tarea no encontrada.")
    ya_existe = db.query(Entrega).filter(Entrega.tarea_id == tarea_id, Entrega.alumno_id == current_user.id).first()
    if ya_existe:
        if (ya_existe.descripcion, ya_existe.comentario, ya_existe.archivo_id) != (payload.descripcion, payload.comentario, payload.archivoId):
            raise HTTPException(409, "Ya existe una entrega con otros datos.")
        return _tarea_to_out(tarea, ya_existe)
    practica = db.query(Practica).filter(Practica.aula_id == aula_id, Practica.practicante_id == current_user.id).order_by(Practica.id).populate_existing().with_for_update().all()
    if any(p.estado == PracticaEstadoEnum.CERRADA for p in practica):
        raise HTTPException(409, "La práctica está cerrada; no admite nuevas entregas.")
    if tarea.aula.estado != AulaEstadoEnum.ACTIVA:
        raise HTTPException(409, "El aula está concluida.")
    if tarea.fecha_limite and _utc(tarea.fecha_limite) < datetime.now(timezone.utc):
        raise HTTPException(422, "El plazo de entrega ya terminó.")
    if payload.archivoId:
        archivo = db.query(Archivo).filter(Archivo.id == payload.archivoId, Archivo.aula_id == aula_id, Archivo.subido_por_id == current_user.id).first()
        if archivo is None:
            raise HTTPException(404, "Archivo no disponible para esta entrega.")
    entrega = Entrega(
        id="ent-" + sha256(f"{tarea_id}:{current_user.id}".encode()).hexdigest(),
        tarea_id=tarea_id, alumno_id=current_user.id,
        descripcion=payload.descripcion, comentario=payload.comentario,
        archivo_id=payload.archivoId, estado=EntregaEstadoEnum.ENTREGADA,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entrega)
    db.commit()
    db.refresh(entrega)
    return _tarea_to_out(tarea, entrega)


# ── GET /api/v1/alumno/aulas/{aula_id}/calificaciones ────────────────────────


@router.get("/alumno/aulas/{aula_id}/calificaciones", response_model=CalificacionesOut)
def get_calificaciones(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve el resumen de calificaciones del alumno en el aula."""
    _solo_alumno(current_user)
    _verificar_inscripcion(aula_id, current_user.id, db)

    tareas = db.query(Tarea).filter(Tarea.aula_id == aula_id).all()
    tareas_total = len(tareas)

    entregas_por_tarea: dict[str, Entrega] = {}
    for e in (
        db.query(Entrega)
        .filter(
            Entrega.alumno_id == current_user.id,
            Entrega.tarea_id.in_([t.id for t in tareas]),
        )
        .all()
    ):
        entregas_por_tarea[e.tarea_id] = e

    notas = [
        e.nota
        for e in entregas_por_tarea.values()
        if e.nota is not None
    ]
    promedio = round(sum(notas) / len(notas), 2) if notas else None

    detalle = []
    for t in tareas:
        e = entregas_por_tarea.get(t.id)
        detalle.append(
            DetalleCalificacionOut(
                tareaId=t.id,
                tareaTitulo=t.titulo,
                nota=e.nota if e else None,
                retroalimentacion=e.retroalimentacion if e else None,
                estado=e.estado.value if e else "PENDIENTE",
                entregadaEn=e.created_at.isoformat() if e and e.created_at else None,
            )
        )

    return CalificacionesOut(
        promedio=promedio,
        tareasTotal=tareas_total,
        tareasEntregadas=len(entregas_por_tarea),
        detalle=detalle,
    )


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _aula_docente(aula_id, user, db, lock=False):
    if user.role.value not in {"PROFESOR", "ADMIN"}:
        raise HTTPException(403, "Solo el docente puede gestionar tareas.")
    query = db.query(Aula).filter(Aula.id == aula_id)
    if user.role.value == "PROFESOR":
        query = query.filter(Aula.profesor_id == user.id)
    if lock:
        query = query.populate_existing().with_for_update()
    aula = query.first()
    if aula is None:
        raise HTTPException(404, "Aula no disponible para tu cuenta.")
    return aula


@router.get("/tareas/capacidades")
def capacidades_tareas(current_user: User = Depends(get_current_user)):
    return {"versionTareas": 1, "entregaTexto": True}


@router.get("/profesor/aulas/{aula_id}/tareas", response_model=list[TareaAlumnoOut])
def list_tareas_docente(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_docente(aula_id, current_user, db)
    return [_tarea_to_out(t, None) for t in db.query(Tarea).filter(Tarea.aula_id == aula_id).order_by(Tarea.created_at.desc()).all()]


@router.post("/profesor/aulas/{aula_id}/tareas", response_model=TareaAlumnoOut, status_code=201)
def create_tarea(aula_id: str, payload: CreateTareaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_docente(aula_id, current_user, db, lock=True)
    task_id = "t-" + payload.solicitudId
    existing = db.get(Tarea, task_id)
    if existing:
        saved_deadline = _utc(existing.fecha_limite) if existing.fecha_limite else None
        if (existing.aula_id, existing.titulo, existing.descripcion, saved_deadline) != (aula_id, payload.titulo, payload.descripcion, payload.fechaLimite):
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _tarea_to_out(existing, None)
    if aula.estado != AulaEstadoEnum.ACTIVA:
        raise HTTPException(409, "El aula está concluida.")
    if payload.fechaLimite and payload.fechaLimite <= datetime.now(timezone.utc):
        raise HTTPException(422, "La fecha límite debe ser futura.")
    task = Tarea(id=task_id, aula_id=aula_id, titulo=payload.titulo, descripcion=payload.descripcion, fecha_limite=payload.fechaLimite)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _tarea_to_out(task, None)
