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
from app.schemas.schemas import AnuncioOut, ContactoOut, CreateAnuncioRequest, CreateForoMensajeRequest, CreateHiloRequest, EnviarMensajeRequest, ForoHiloOut, ForoMensajeOut, MensajeDirectoOut

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


# ── HU-38 · Mensajería directa ────────────────────────────────────────────────


@router.get("/aulas/{aula_id}/contactos", response_model=list[ContactoOut])
def list_contactos(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Interlocutores disponibles en el aula: para el profesor, los alumnos inscritos;
    para el alumno, el profesor del aula. Incluye el conteo de mensajes sin leer.
    """
    aula = _aula_con_acceso(aula_id, current_user, db)

    if _es_docente(current_user, aula):
        inscripciones = db.query(Inscripcion).filter(Inscripcion.aula_id == aula_id).all()
        otros = [ins.alumno for ins in inscripciones]
    else:
        otros = [aula.profesor] if aula.profesor else []

    contactos = []
    for u in otros:
        no_leidos = (
            db.query(MensajeDirecto)
            .filter(
                MensajeDirecto.aula_id == aula_id,
                MensajeDirecto.remitente_id == u.id,
                MensajeDirecto.destinatario_id == current_user.id,
                MensajeDirecto.leido == 0,
            )
            .count()
        )
        contactos.append(
            ContactoOut(
                userId=u.id,
                nombre=_nombre(u),
                aulaId=aula_id,
                aulaNombre=aula.nombre,
                noLeidos=no_leidos,
            )
        )
    contactos.sort(key=lambda c: (-c.noLeidos, c.nombre))
    return contactos


@router.get("/aulas/{aula_id}/mensajes/{otro_id}", response_model=list[MensajeDirectoOut])
def conversacion(
    aula_id: str,
    otro_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Conversación con otro usuario del aula. Marca como leídos los mensajes entrantes."""
    _aula_con_acceso(aula_id, current_user, db)

    mensajes = (
        db.query(MensajeDirecto)
        .filter(
            MensajeDirecto.aula_id == aula_id,
            MensajeDirecto.remitente_id.in_([current_user.id, otro_id]),
            MensajeDirecto.destinatario_id.in_([current_user.id, otro_id]),
        )
        .order_by(MensajeDirecto.created_at.asc())
        .all()
    )

    # Marca como leídos los mensajes que me envió el otro.
    cambiados = False
    for m in mensajes:
        if m.destinatario_id == current_user.id and not m.leido:
            m.leido = 1
            cambiados = True
    if cambiados:
        db.commit()

    return [
        MensajeDirectoOut(
            id=m.id,
            remitenteId=m.remitente_id,
            remitenteNombre=_nombre(m.remitente) if m.remitente else "",
            texto=m.texto,
            mio=m.remitente_id == current_user.id,
            fecha=m.created_at.isoformat() if m.created_at else "",
        )
        for m in mensajes
    ]


@router.post(
    "/aulas/{aula_id}/mensajes/{otro_id}",
    response_model=MensajeDirectoOut,
    status_code=status.HTTP_201_CREATED,
)
def enviar_mensaje(
    aula_id: str,
    otro_id: str,
    payload: EnviarMensajeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Envía un mensaje directo a otro usuario del aula."""
    _aula_con_acceso(aula_id, current_user, db)
    destinatario = db.query(User).filter(User.id == otro_id).first()
    if destinatario is None:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado.")
    texto = payload.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacío.")

    msg = MensajeDirecto(
        aula_id=aula_id,
        remitente_id=current_user.id,
        destinatario_id=otro_id,
        texto=texto,
        leido=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MensajeDirectoOut(
        id=msg.id,
        remitenteId=msg.remitente_id,
        remitenteNombre=_nombre(current_user),
        texto=msg.texto,
        mio=True,
        fecha=msg.created_at.isoformat(),
    )
