"""Bandeja privada de avisos y lectura explícita. No envía notificaciones push."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, func, case
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Notificacion, User
from app.schemas.schemas import NotificacionOut, DestinoTarea, DestinoActividad

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def _to_out(n):
    target = None
    try:
        if isinstance(n.destino, dict):
            kind = n.destino.get("tipo")
            model = {"TAREA": DestinoTarea, "ACTIVIDAD": DestinoActividad}.get(kind) if isinstance(kind, str) else None
            if model:
                target = model.model_validate(n.destino)
    except ValidationError:
        pass  # Un destino antiguo incompatible no inutiliza el texto del aviso.
    return NotificacionOut(id=n.id, userId=n.user_id, tipo=n.tipo.value,
        titulo=n.titulo, mensaje=n.mensaje, leida=bool(n.leida),
        fecha=n.fecha.isoformat() if n.fecha else "", destino=target)


def _owned(db, user, notice_id):
    n = db.query(Notificacion).filter(Notificacion.id == notice_id, Notificacion.user_id == user.id).first()
    if n is None:
        raise HTTPException(404, "El aviso no está disponible para tu cuenta.")
    return n


@router.get("", response_model=list[NotificacionOut])
def list_notificaciones(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Compatibilidad con clientes anteriores; la app nueva usa /bandeja."""
    return [_to_out(n) for n in db.query(Notificacion).filter(Notificacion.user_id == current_user.id)
        .order_by(Notificacion.fecha.desc().nullslast(), Notificacion.id.desc()).all()]


class BandejaOut(BaseModel):
    items: list[NotificacionOut]
    total: int
    sinLeer: int
    siguiente: str | None


@router.get("/bandeja", response_model=BandejaOut)
def bandeja(estado: Literal["todos", "pendientes", "leidos"] = "todos",
    limite: int = Query(20, ge=1, le=50), cursor: str | None = Query(None, max_length=400),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    own = db.query(Notificacion).filter(Notificacion.user_id == current_user.id)
    total, unread = db.query(func.count(Notificacion.id), func.coalesce(func.sum(
        case((Notificacion.leida == 0, 1), else_=0)), 0)).filter(Notificacion.user_id == current_user.id).one()
    query = own
    if estado != "todos":
        query = query.filter(Notificacion.leida == (0 if estado == "pendientes" else 1))
    if cursor:
        try:
            raw_date, last_id = cursor.split("|", 1)
            if not last_id or len(last_id) > 200:
                raise ValueError()
            date = datetime.fromisoformat(raw_date) if raw_date else None
            if date and date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise HTTPException(422, "El punto de continuación no es válido. Actualiza tus avisos.")
        if date is None:
            query = query.filter(Notificacion.fecha.is_(None), Notificacion.id < last_id)
        else:
            query = query.filter(or_(Notificacion.fecha < date,
                and_(Notificacion.fecha == date, Notificacion.id < last_id), Notificacion.fecha.is_(None)))
    rows = query.order_by(Notificacion.fecha.desc().nullslast(), Notificacion.id.desc()).limit(limite + 1).all()
    more = len(rows) > limite
    rows = rows[:limite]
    next_cursor = f"{rows[-1].fecha.isoformat() if rows[-1].fecha else ''}|{rows[-1].id}" if more else None
    matches = total if estado == "todos" else unread if estado == "pendientes" else total - unread
    return BandejaOut(items=[_to_out(n) for n in rows], total=matches, sinLeer=unread, siguiente=next_cursor)


@router.put("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notificacion).filter(Notificacion.user_id == current_user.id, Notificacion.leida == 0).update({Notificacion.leida: 1})
    db.commit()


@router.get("/{notif_id}", response_model=NotificacionOut)
def get_notificacion(notif_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _to_out(_owned(db, current_user, notif_id))


@router.put("/{notif_id}/read", status_code=204)
def mark_read(notif_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    n = _owned(db, current_user, notif_id)
    n.leida = 1
    db.commit()
