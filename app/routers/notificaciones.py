"""
Notificaciones de tareas asignadas y vencimientos próximos (HU-17).
Rutas: /api/v1/notificaciones/*
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Notificacion, User
from app.schemas.schemas import NotificacionOut

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


def _to_out(n: Notificacion) -> NotificacionOut:
    return NotificacionOut(
        id=n.id,
        userId=n.user_id,
        tipo=n.tipo.value,
        titulo=n.titulo,
        mensaje=n.mensaje,
        leida=bool(n.leida),
        fecha=n.fecha.isoformat() if n.fecha else "",
    )


# ── GET /api/v1/notificaciones ────────────────────────────────────────────────


@router.get("", response_model=list[NotificacionOut])
def list_notificaciones(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Notificaciones del usuario autenticado, más recientes primero."""
    notifs = (
        db.query(Notificacion)
        .filter(Notificacion.user_id == current_user.id)
        .order_by(Notificacion.fecha.desc())
        .all()
    )
    return [_to_out(n) for n in notifs]


# ── PUT /api/v1/notificaciones/read-all ───────────────────────────────────────


@router.put("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca todas las notificaciones del usuario como leídas."""
    db.query(Notificacion).filter(
        Notificacion.user_id == current_user.id
    ).update({Notificacion.leida: 1})
    db.commit()


# ── PUT /api/v1/notificaciones/{notif_id}/read ────────────────────────────────


@router.put("/{notif_id}/read", status_code=204)
def mark_read(
    notif_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca una notificación puntual como leída."""
    db.query(Notificacion).filter(
        Notificacion.id == notif_id,
        Notificacion.user_id == current_user.id,
    ).update({Notificacion.leida: 1})
    db.commit()
