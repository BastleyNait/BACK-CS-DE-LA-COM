"""Comunicación por pertenencia al aula; escrituras idempotentes y auditadas."""
import hashlib
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Anuncio, Aula, AulaEstadoEnum, Auditoria, ForoHilo, ForoMensaje, Inscripcion, MensajeDirecto, User
from app.schemas.schemas import AnuncioOut, ContactoOut, CreateAnuncioRequest, CreateForoMensajeRequest, CreateHiloRequest, EnviarMensajeRequest, ForoHiloOut, ForoMensajeOut, MensajeDirectoOut, LeerMensajesRequest

router = APIRouter(tags=["comunicacion"])


def _aula_con_acceso(aula_id: str, user: User, db: Session, lock=False) -> Aula:
    query = db.query(Aula).filter(Aula.id == aula_id)
    if lock:
        query = query.populate_existing().with_for_update()
    aula = query.first()
    if aula is None:
        raise HTTPException(404, "Aula no encontrada.")
    role = user.role.value
    if role == "ADMIN" or role == "PROFESOR" and aula.profesor_id == user.id:
        return aula
    if role == "ALUMNO" and db.query(Inscripcion).filter(Inscripcion.alumno_id == user.id, Inscripcion.aula_id == aula_id).first():
        return aula
    raise HTTPException(403, "No tienes acceso a esta aula.")


def _es_docente(user, aula):
    return user.role.value == "ADMIN" or user.role.value == "PROFESOR" and aula.profesor_id == user.id


def _nombre(user):
    return f"{user.nombres} {user.apellidos}"


def _open(aula):
    if aula.estado != AulaEstadoEnum.ACTIVA:
        raise HTTPException(409, "El aula está concluida; el contenido es de consulta.")


def _id(prefix, user, parent, key):
    return prefix + "-" + (hashlib.sha256(f"{user.id}:{parent}:{key}".encode()).hexdigest() if key else uuid.uuid4().hex)


def _audit(db, user, accion, detalle):
    db.add(Auditoria(user_id=user.id, user_nombre=_nombre(user), accion=accion, detalle=detalle))


def _anuncio(a):
    return AnuncioOut(id=a.id, aulaId=a.aula_id, autorNombre=a.autor_nombre, titulo=a.titulo, mensaje=a.mensaje, fijado=bool(a.fijado), fecha=a.created_at.isoformat())


def _hilo(h, respuestas):
    return ForoHiloOut(id=h.id, aulaId=h.aula_id, autorNombre=h.autor_nombre, titulo=h.titulo, respuestas=respuestas, fecha=h.created_at.isoformat())


def _mensaje(m):
    return ForoMensajeOut(id=m.id, hiloId=m.hilo_id, autorNombre=m.autor_nombre, texto=m.texto, fecha=m.created_at.isoformat())


@router.get("/comunicacion/capacidades")
def capacidades(current_user: User = Depends(get_current_user)):
    return {"versionComunicacion": 1}


@router.get("/comunicacion/aulas")
def aulas_comunicacion(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Aula)
    if current_user.role.value == "ALUMNO":
        query = query.filter(Aula.id.in_(select(Inscripcion.aula_id).where(Inscripcion.alumno_id == current_user.id)))
    elif current_user.role.value == "PROFESOR":
        query = query.filter(Aula.profesor_id == current_user.id)
    elif current_user.role.value != "ADMIN":
        raise HTTPException(403, "Sección para miembros del aula.")
    return [{"id": a.id, "nombre": a.nombre, "periodo": a.periodo, "estado": a.estado.value} for a in query.order_by(Aula.nombre, Aula.id).all()]


@router.get("/aulas/{aula_id}/anuncios", response_model=list[AnuncioOut])
def list_anuncios(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    return [_anuncio(a) for a in db.query(Anuncio).filter(Anuncio.aula_id == aula_id).order_by(Anuncio.fijado.desc(), Anuncio.created_at.desc(), Anuncio.id).all()]


@router.post("/aulas/{aula_id}/anuncios", response_model=AnuncioOut, status_code=201)
def crear_anuncio(aula_id: str, payload: CreateAnuncioRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db, lock=True)
    if not _es_docente(current_user, aula):
        raise HTTPException(403, "Solo el docente del aula o administración puede publicar.")
    record_id = _id("an", current_user, aula_id, payload.solicitudId)
    existing = db.get(Anuncio, record_id)
    if existing:
        if (existing.titulo, existing.mensaje, bool(existing.fijado)) != (payload.titulo, payload.mensaje, payload.fijado):
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _anuncio(existing)
    _open(aula)
    anuncio = Anuncio(id=record_id, aula_id=aula_id, autor_id=current_user.id, autor_nombre=_nombre(current_user), titulo=payload.titulo, mensaje=payload.mensaje, fijado=int(payload.fijado), created_at=datetime.now(timezone.utc))
    db.add(anuncio)
    _audit(db, current_user, "ANUNCIO_PUBLICADO", f"{aula.nombre}: {payload.titulo}")
    db.commit()
    return _anuncio(anuncio)


@router.delete("/aulas/{aula_id}/anuncios/{anuncio_id}", status_code=204)
def eliminar_anuncio(aula_id: str, anuncio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db, lock=True)
    if not _es_docente(current_user, aula):
        raise HTTPException(403, "Solo el docente del aula o administración puede eliminar.")
    _open(aula)
    anuncio = db.query(Anuncio).filter(Anuncio.id == anuncio_id, Anuncio.aula_id == aula_id).first()
    if not anuncio:
        raise HTTPException(404, "Anuncio no encontrado.")
    _audit(db, current_user, "ANUNCIO_ELIMINADO", f"{aula.nombre}: {anuncio.titulo}")
    db.delete(anuncio)
    db.commit()


@router.get("/aulas/{aula_id}/foros", response_model=list[ForoHiloOut])
def list_hilos(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    rows = db.query(ForoHilo, func.count(ForoMensaje.id)).outerjoin(ForoMensaje, ForoMensaje.hilo_id == ForoHilo.id).filter(ForoHilo.aula_id == aula_id).group_by(ForoHilo.id).order_by(ForoHilo.created_at.desc(), ForoHilo.id).all()
    return [_hilo(h, count) for h, count in rows]


@router.post("/aulas/{aula_id}/foros", response_model=ForoHiloOut, status_code=201)
def crear_hilo(aula_id: str, payload: CreateHiloRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db, lock=True)
    record_id = _id("fh", current_user, aula_id, payload.solicitudId)
    existing = db.get(ForoHilo, record_id)
    if existing:
        if existing.titulo != payload.titulo:
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _hilo(existing, db.query(ForoMensaje).filter(ForoMensaje.hilo_id == existing.id).count())
    _open(aula)
    hilo = ForoHilo(id=record_id, aula_id=aula_id, autor_id=current_user.id, autor_nombre=_nombre(current_user), titulo=payload.titulo, created_at=datetime.now(timezone.utc))
    db.add(hilo)
    _audit(db, current_user, "FORO_CREADO", f"{aula.nombre}: {payload.titulo}")
    db.commit()
    return _hilo(hilo, 0)


@router.get("/foros/{hilo_id}/mensajes", response_model=list[ForoMensajeOut])
def list_mensajes_hilo(hilo_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    hilo = db.get(ForoHilo, hilo_id)
    if hilo is None:
        raise HTTPException(404, "Hilo no encontrado.")
    _aula_con_acceso(hilo.aula_id, current_user, db)
    return [_mensaje(m) for m in db.query(ForoMensaje).filter(ForoMensaje.hilo_id == hilo_id).order_by(ForoMensaje.created_at, ForoMensaje.id).all()]


@router.post("/foros/{hilo_id}/mensajes", response_model=ForoMensajeOut, status_code=201)
def responder_hilo(hilo_id: str, payload: CreateForoMensajeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    hilo = db.get(ForoHilo, hilo_id)
    if hilo is None:
        raise HTTPException(404, "Hilo no encontrado.")
    aula = _aula_con_acceso(hilo.aula_id, current_user, db, lock=True)
    record_id = _id("fm", current_user, hilo_id, payload.solicitudId)
    existing = db.get(ForoMensaje, record_id)
    if existing:
        if existing.texto != payload.texto:
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _mensaje(existing)
    _open(aula)
    msg = ForoMensaje(id=record_id, hilo_id=hilo_id, autor_id=current_user.id, autor_nombre=_nombre(current_user), texto=payload.texto, created_at=datetime.now(timezone.utc))
    db.add(msg)
    _audit(db, current_user, "FORO_RESPUESTA", f"{aula.nombre}: respuesta en {hilo.titulo}")
    db.commit()
    return _mensaje(msg)


# ── Mensajería académica privada entre docente responsable y alumno matriculado ──


def _message_member(user):
    if user.role.value not in {"ALUMNO", "PROFESOR"}:
        raise HTTPException(403, "La mensajería académica vincula docente y alumno del aula.")


def _peer(aula, user, otro_id, db):
    _message_member(user)
    if otro_id == user.id:
        raise HTTPException(403, "Elige otro participante.")
    peer = db.query(User).filter(User.id == otro_id).populate_existing().first()
    if peer is None:
        raise HTTPException(404, "Contacto no disponible.")
    teacher, student = (user, peer) if user.role.value == "PROFESOR" else (peer, user)
    if (teacher.id != aula.profesor_id or teacher.role.value != "PROFESOR" or student.role.value != "ALUMNO"
            or not db.query(Inscripcion).filter(Inscripcion.aula_id == aula.id, Inscripcion.alumno_id == student.id).first()):
        raise HTTPException(403, "El contacto no pertenece al vínculo docente/alumno de esta aula.")
    return peer


def _direct(m, user):
    return MensajeDirectoOut(id=m.id, aulaId=m.aula_id, destinatarioId=m.destinatario_id,
        remitenteId=m.remitente_id, remitenteNombre=_nombre(m.remitente), texto=m.texto,
        mio=m.remitente_id == user.id, leido=bool(m.leido), fecha=m.created_at.isoformat())


@router.get("/mensajes/capacidades")
def capacidades_mensajes(current_user: User = Depends(get_current_user)):
    _message_member(current_user)
    return {"versionMensajes": 1, "lecturaExplicita": True}


@router.get("/aulas/{aula_id}/contactos", response_model=list[ContactoOut])
def list_contactos(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _message_member(current_user)
    aula = _aula_con_acceso(aula_id, current_user, db)
    if current_user.role.value == "PROFESOR":
        users = db.query(User).filter(User.id.in_(select(Inscripcion.alumno_id).where(Inscripcion.aula_id == aula_id)), User.role == "ALUMNO").all()
    else:
        users = [aula.profesor] if aula.profesor and aula.profesor.role.value == "PROFESOR" else []
    counts = dict(db.query(MensajeDirecto.remitente_id, func.count(MensajeDirecto.id)).filter(
        MensajeDirecto.aula_id == aula_id, MensajeDirecto.destinatario_id == current_user.id, MensajeDirecto.leido == 0).group_by(MensajeDirecto.remitente_id).all())
    return sorted([ContactoOut(userId=u.id, nombre=_nombre(u), aulaId=aula.id, aulaNombre=aula.nombre, noLeidos=counts.get(u.id, 0)) for u in users], key=lambda c: (-c.noLeidos, c.nombre, c.userId))


@router.get("/aulas/{aula_id}/mensajes/{otro_id}", response_model=list[MensajeDirectoOut])
def conversacion(aula_id: str, otro_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db)
    _peer(aula, current_user, otro_id, db)
    return [_direct(m, current_user) for m in db.query(MensajeDirecto).filter(MensajeDirecto.aula_id == aula_id,
        MensajeDirecto.remitente_id.in_([current_user.id, otro_id]), MensajeDirecto.destinatario_id.in_([current_user.id, otro_id])).order_by(MensajeDirecto.created_at, MensajeDirecto.id).all()]


@router.post("/aulas/{aula_id}/mensajes/{otro_id}", response_model=MensajeDirectoOut, status_code=201)
def enviar_mensaje(aula_id: str, otro_id: str, payload: EnviarMensajeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db, lock=True)
    peer = _peer(aula, current_user, otro_id, db)
    record_id = _id("md", current_user, f"{aula_id}:{otro_id}", payload.solicitudId)
    existing = db.get(MensajeDirecto, record_id)
    if existing:
        if existing.texto != payload.texto:
            raise HTTPException(409, "La solicitud ya se utilizó con otro contenido.")
        return _direct(existing, current_user)
    _open(aula)
    msg = MensajeDirecto(id=record_id, aula_id=aula_id, remitente_id=current_user.id, destinatario_id=otro_id,
                        texto=payload.texto, leido=0, created_at=datetime.now(timezone.utc))
    db.add(msg)
    _audit(db, current_user, "MENSAJE_ENVIADO", f"{aula.nombre}: mensaje de {_nombre(current_user)} a {_nombre(peer)}. El contenido permanece en la conversación privada.")
    db.commit()
    return _direct(msg, current_user)


@router.put("/aulas/{aula_id}/mensajes/{otro_id}/lectura")
def marcar_lectura(aula_id: str, otro_id: str, payload: LeerMensajesRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db, lock=True)
    _peer(aula, current_user, otro_id, db)
    rows = db.query(MensajeDirecto).filter(MensajeDirecto.id.in_(payload.mensajeIds), MensajeDirecto.aula_id == aula_id,
        MensajeDirecto.remitente_id == otro_id, MensajeDirecto.destinatario_id == current_user.id).populate_existing().with_for_update().all()
    if len(rows) != len(payload.mensajeIds):
        raise HTTPException(404, "Uno de los mensajes no está disponible para marcarlo como leído.")
    if any(not row.leido for row in rows):
        for row in rows: row.leido = 1
        db.commit()
    return {"mensajeIds": payload.mensajeIds}
