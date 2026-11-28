"""Web Push: los avisos se envían solo después de confirmar la transacción que los creó."""
import json
import logging
from urllib.parse import urlencode
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.core.config import settings

log = logging.getLogger(__name__)


def enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY.get_secret_value())


def target_url(target):
    target = target or {}
    if target.get("tipo") == "TAREA" and target.get("aulaId") and target.get("tareaId"):
        return "/tarea?" + urlencode({"aulaId": target["aulaId"], "tareaId": target["tareaId"]})
    if target.get("tipo") == "ACTIVIDAD" and target.get("practicaId") and target.get("registroId"):
        return "/actividad?" + urlencode({"practicaId": target["practicaId"], "registroId": target["registroId"]})
    return "/"


def queue_push(db, user_id, title, message, target):
    if enabled():
        db.info.setdefault("push", []).append((user_id, title, message[:300], target_url(target)))


@event.listens_for(Session, "after_rollback")
def _discard(session):
    session.info.pop("push", None)


@event.listens_for(Session, "after_commit")
def _send_after_commit(session):
    pending = session.info.pop("push", None)
    if pending:
        deliver(pending, session.get_bind())


def deliver(pending, bind):
    """Envía con una sesión nueva; un fallo de push nunca afecta al evento académico ya confirmado."""
    from pywebpush import WebPushException, webpush
    from app.models.models import SuscripcionPush
    db = Session(bind=bind)
    try:
        for user_id, title, message, url in pending:
            for sub in db.query(SuscripcionPush).filter(SuscripcionPush.user_id == user_id).limit(10).all():
                try:
                    webpush({"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                            json.dumps({"title": title, "body": message, "url": url}),
                            vapid_private_key=settings.VAPID_PRIVATE_KEY.get_secret_value(),
                            vapid_claims={"sub": settings.VAPID_SUBJECT}, timeout=5, ttl=86400)
                except WebPushException as error:
                    if getattr(error.response, "status_code", None) in (404, 410):
                        db.delete(sub)  # El navegador retiró la suscripción.
                except Exception:
                    log.warning("No se pudo enviar una notificación push.")
        db.commit()
    except Exception:
        db.rollback()
        log.warning("Envío push omitido.")
    finally:
        db.close()
