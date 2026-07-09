"""
Tareas y entregas del alumno (HU-09 entrega / HU-10 calificaciones).
Rutas: /api/v1/alumno/aulas/{aula_id}/tareas/*
       /api/v1/alumno/aulas/{aula_id}/calificaciones
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    Archivo,
    Entrega,
    EntregaEstadoEnum,
    Inscripcion,
    Tarea,
    User,
)
from app.schemas.schemas import (
    CalificacionesOut,
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

    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.aula_id == aula_id).first()
    if tarea is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")

    ya_existe = (
        db.query(Entrega)
        .filter(Entrega.tarea_id == tarea_id, Entrega.alumno_id == current_user.id)
        .first()
    )
    if ya_existe:
        raise HTTPException(status_code=409, detail="Ya entregaste esta tarea.")

    if payload.archivoId:
        archivo = db.query(Archivo).filter(Archivo.id == payload.archivoId).first()
        if archivo is None:
            raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    entrega = Entrega(
        tarea_id=tarea_id,
        alumno_id=current_user.id,
        descripcion=payload.descripcion,
        comentario=payload.comentario,
        archivo_id=payload.archivoId,
        estado=EntregaEstadoEnum.ENTREGADA,
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
