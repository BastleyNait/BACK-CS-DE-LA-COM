"""Suscripciones Web Push del navegador del usuario."""
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.push import enabled
from app.db.session import get_db
from app.models.models import SuscripcionPush, User

router = APIRouter(prefix="/push", tags=["push"])


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class Subscription(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2000, pattern=r"^https://")
    keys: Keys


class Unsubscribe(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2000)


@router.get("/capacidades")
def capacidades():
    return {"web": enabled(), "clave": settings.VAPID_PUBLIC_KEY if enabled() else None}


@router.post("/suscripciones", status_code=201)
def suscribir(body: Subscription, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not enabled():
        raise HTTPException(503, "Las notificaciones push no están configuradas en este servidor.")
    key = sha256(body.endpoint.encode()).hexdigest()
    row = db.get(SuscripcionPush, key)
    if row is None:
        if db.query(SuscripcionPush).filter(SuscripcionPush.user_id == current_user.id).count() >= 10:
            raise HTTPException(409, "Ya activaste las notificaciones en 10 navegadores. Desactiva alguno.")
        db.add(SuscripcionPush(id=key, user_id=current_user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth))
    else:
        # Un navegador compartido pasa a la cuenta que lo activó por última vez.
        row.user_id, row.p256dh, row.auth = current_user.id, body.keys.p256dh, body.keys.auth
    db.commit()
    return {"activo": True}


@router.post("/suscripciones/baja")
def dar_baja(body: Unsubscribe, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.get(SuscripcionPush, sha256(body.endpoint.encode()).hexdigest())
    if row and row.user_id == current_user.id:
        db.delete(row)
        db.commit()
    return {"activo": False}
