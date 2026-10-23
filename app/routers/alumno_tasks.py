"""Tareas del alumno por páginas y detalle individual; sin cambios de esquema."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, func, case
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Tarea, Entrega, EntregaEstadoEnum, Practica, PracticaEstadoEnum, CambioTarea, VersionEntrega
from app.routers.tareas import _solo_alumno, _verificar_inscripcion, _utc
from app.schemas.schemas import TareaAlumnoOut, EntregaOut

router = APIRouter(prefix="/alumno/aulas", tags=["alumno"])


def owned_aula(db, user, aula_id):
    _solo_alumno(user)
    _verificar_inscripcion(aula_id, user.id, db)


@router.get("/{aula_id}/tareas/pagina")
def task_page(aula_id: str, estado: Literal["todas", "pendientes", "entregadas", "calificadas"] = "pendientes",
    limite: int = Query(20, ge=1, le=50), cursor: str | None = Query(None, max_length=400),
    db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    owned_aula(db, current_user, aula_id)
    own_delivery = and_(Entrega.tarea_id == Tarea.id, Entrega.alumno_id == current_user.id)
    total, delivered, graded, average = db.query(func.count(Tarea.id), func.count(Entrega.id),
        func.coalesce(func.sum(case((Entrega.estado == EntregaEstadoEnum.CALIFICADA, 1), else_=0)), 0),
        func.avg(Entrega.nota)).outerjoin(Entrega, own_delivery).filter(Tarea.aula_id == aula_id).one()
    summary = {"total": total, "pendientes": total - delivered, "entregadas": delivered,
        "calificadas": graded, "promedio": round(float(average), 2) if average is not None else None}
    # La fila de lista no carga descripción, archivos ni versiones de las entregas.
    query = db.query(Tarea.id, Tarea.titulo, Tarea.fecha_limite, Entrega.estado, Entrega.nota).outerjoin(
        Entrega, own_delivery).filter(Tarea.aula_id == aula_id)
    if estado == "pendientes": query = query.filter(Entrega.id.is_(None))
    if estado == "entregadas": query = query.filter(Entrega.id.is_not(None))
    if estado == "calificadas": query = query.filter(Entrega.estado == EntregaEstadoEnum.CALIFICADA)
    if cursor:
        try:
            raw_date, last_id = cursor.split("|", 1)
            if not last_id or len(last_id) > 200: raise ValueError()
            date = datetime.fromisoformat(raw_date) if raw_date else None
            if date and date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise HTTPException(422, "El punto de continuación no es válido. Actualiza las tareas.")
        if date is None:
            query = query.filter(Tarea.fecha_limite.is_(None), Tarea.id > last_id)
        else:
            query = query.filter(or_(Tarea.fecha_limite > date,
                and_(Tarea.fecha_limite == date, Tarea.id > last_id), Tarea.fecha_limite.is_(None)))
    rows = query.order_by(Tarea.fecha_limite.asc().nullslast(), Tarea.id.asc()).limit(limite + 1).all()
    more, rows = len(rows) > limite, rows[:limite]
    next_cursor = f"{rows[-1].fecha_limite.isoformat() if rows[-1].fecha_limite else ''}|{rows[-1].id}" if more else None
    items = [{"id": r.id, "aulaId": aula_id, "titulo": r.titulo,
        "fechaLimite": r.fecha_limite.isoformat() if r.fecha_limite else None,
        "estado": r.estado.value if r.estado else "PENDIENTE", "nota": r.nota} for r in rows]
    return {"items": items, "resumen": summary, "total": total if estado == "todas" else summary[estado], "siguiente": next_cursor}


class StudentTaskOut(TareaAlumnoOut):
    aulaNombre: str
    entregaHabilitada: bool
    bloqueoEntrega: str | None


@router.get("/{aula_id}/tareas/{tarea_id}", response_model=StudentTaskOut)
def task_detail(aula_id: str, tarea_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    owned_aula(db, current_user, aula_id)
    task = db.query(Tarea).filter(Tarea.aula_id == aula_id, Tarea.id == tarea_id).first()
    if task is None: raise HTTPException(404, "La tarea no está disponible en esta aula.")
    delivery = db.query(Entrega).filter(Entrega.tarea_id == task.id, Entrega.alumno_id == current_user.id).first()
    closed = db.query(Practica.id).filter(Practica.aula_id == aula_id, Practica.practicante_id == current_user.id,
        Practica.estado == PracticaEstadoEnum.CERRADA).first()
    reason = None
    if delivery and delivery.estado == EntregaEstadoEnum.CALIFICADA:
        reason = "Tu entrega ya está calificada y se conserva para consulta."
    elif closed:
        reason = "Tu práctica está cerrada y se conserva para consulta."
    elif task.aula.estado.value != "ACTIVA":
        reason = "El aula está concluida y se conserva para consulta."
    elif task.fecha_limite and _utc(task.fecha_limite) < datetime.now(timezone.utc):
        reason = "El plazo de entrega terminó. Consulta con tu docente si necesitas una ampliación."
    # Consultar la revisión actual no necesita cargar el contenido de las versiones anteriores.
    revision = db.query(func.coalesce(func.max(CambioTarea.revision), 0)).filter(CambioTarea.tarea_id == task.id).scalar()
    delivered = None
    if delivery:
        delivery_revision = db.query(func.coalesce(func.max(VersionEntrega.revision), 0)).filter(VersionEntrega.entrega_id == delivery.id).scalar()
        delivered = EntregaOut(id=delivery.id, revision=delivery_revision, tareaId=task.id, alumnoId=current_user.id,
            descripcion=delivery.descripcion, comentario=delivery.comentario, archivoId=delivery.archivo_id,
            estado=delivery.estado.value, nota=delivery.nota, retroalimentacion=delivery.retroalimentacion,
            createdAt=delivery.created_at.isoformat() if delivery.created_at else "")
    return StudentTaskOut(id=task.id, revision=revision, aulaId=aula_id, titulo=task.titulo, descripcion=task.descripcion,
        fechaLimite=task.fecha_limite.isoformat() if task.fecha_limite else None,
        createdAt=task.created_at.isoformat() if task.created_at else "", entrega=delivered,
        aulaNombre=task.aula.nombre, entregaHabilitada=reason is None, bloqueoEntrega=reason)
