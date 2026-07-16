"""
Comunicación del aula: anuncios (HU-36), foros (HU-37) y mensajería directa (HU-38).
Rutas: /api/v1/aulas/{aula_id}/anuncios, /foros, /contactos, /mensajes …
El acceso al aula se valida por rol (profesor dueño, admin o alumno inscrito).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    Anuncio,
    Aula,
    ForoHilo,
    ForoMensaje,
    Inscripcion,
    MensajeDirecto,
    User,
)
from app.schemas.schemas import (
    AnuncioOut,
    ContactoOut,
    CreateAnuncioRequest,
    CreateForoMensajeRequest,
    CreateHiloRequest,
    EnviarMensajeRequest,
    ForoHiloOut,
    ForoMensajeOut,
    MensajeDirectoOut,
)

router = APIRouter(tags=["comunicacion"])


# ── Helpers de acceso ─────────────────────────────────────────────────────────


def _aula_con_acceso(aula_id: str, user: User, db: Session) -> Aula:
    """Aula si el usuario es su profesor, admin o un alumno inscrito; si no, 403/404."""
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if aula is None:
        raise HTTPException(status_code=404, detail="Aula no encontrada.")
    role = user.role.value
    if role == "ADMIN":
        return aula
    if role == "PROFESOR" and aula.profesor_id == user.id:
        return aula
    if role == "ALUMNO":
        ins = (
            db.query(Inscripcion)
            .filter(Inscripcion.alumno_id == user.id, Inscripcion.aula_id == aula_id)
            .first()
        )
        if ins:
            return aula
    raise HTTPException(status_code=403, detail="No tienes acceso a esta aula.")


def _es_docente(user: User, aula: Aula) -> bool:
    return user.role.value == "ADMIN" or (
        user.role.value == "PROFESOR" and aula.profesor_id == user.id
    )


def _nombre(u: User) -> str:
    return f"{u.nombres} {u.apellidos}"


# ── HU-36 · Anuncios ──────────────────────────────────────────────────────────


@router.get("/aulas/{aula_id}/anuncios", response_model=list[AnuncioOut])
def list_anuncios(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anuncios del aula: primero los fijados, luego del más reciente al más antiguo."""
    _aula_con_acceso(aula_id, current_user, db)
    anuncios = (
        db.query(Anuncio)
        .filter(Anuncio.aula_id == aula_id)
        .order_by(Anuncio.fijado.desc(), Anuncio.created_at.desc())
        .all()
    )
    return [
        AnuncioOut(
            id=a.id,
            aulaId=a.aula_id,
            autorNombre=a.autor_nombre,
            titulo=a.titulo,
            mensaje=a.mensaje,
            fijado=bool(a.fijado),
            fecha=a.created_at.isoformat() if a.created_at else "",
        )
        for a in anuncios
    ]


@router.post(
    "/aulas/{aula_id}/anuncios",
    response_model=AnuncioOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_anuncio(
    aula_id: str,
    payload: CreateAnuncioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Publica un anuncio en el aula. Solo el profesor del aula (o admin)."""
    aula = _aula_con_acceso(aula_id, current_user, db)
    if not _es_docente(current_user, aula):
        raise HTTPException(status_code=403, detail="Solo el profesor puede publicar anuncios.")

    anuncio = Anuncio(
        aula_id=aula_id,
        autor_id=current_user.id,
        autor_nombre=_nombre(current_user),
        titulo=payload.titulo,
        mensaje=payload.mensaje,
        fijado=1 if payload.fijado else 0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(anuncio)
    db.commit()
    db.refresh(anuncio)
    return AnuncioOut(
        id=anuncio.id,
        aulaId=anuncio.aula_id,
        autorNombre=anuncio.autor_nombre,
        titulo=anuncio.titulo,
        mensaje=anuncio.mensaje,
        fijado=bool(anuncio.fijado),
        fecha=anuncio.created_at.isoformat(),
    )


@router.delete("/aulas/{aula_id}/anuncios/{anuncio_id}", status_code=204)
def eliminar_anuncio(
    aula_id: str,
    anuncio_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina un anuncio. Solo el profesor del aula (o admin)."""
    aula = _aula_con_acceso(aula_id, current_user, db)
    if not _es_docente(current_user, aula):
        raise HTTPException(status_code=403, detail="Solo el profesor puede eliminar anuncios.")
    anuncio = (
        db.query(Anuncio)
        .filter(Anuncio.id == anuncio_id, Anuncio.aula_id == aula_id)
        .first()
    )
    if anuncio is None:
        raise HTTPException(status_code=404, detail="Anuncio no encontrado.")
    db.delete(anuncio)
    db.commit()


# ── HU-37 · Foros ─────────────────────────────────────────────────────────────


@router.get("/aulas/{aula_id}/foros", response_model=list[ForoHiloOut])
def list_hilos(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los hilos del foro del aula con su número de respuestas."""
    _aula_con_acceso(aula_id, current_user, db)
    hilos = (
        db.query(ForoHilo)
        .filter(ForoHilo.aula_id == aula_id)
        .order_by(ForoHilo.created_at.desc())
        .all()
    )
    out = []
    for h in hilos:
        respuestas = db.query(ForoMensaje).filter(ForoMensaje.hilo_id == h.id).count()
        out.append(
            ForoHiloOut(
                id=h.id,
                aulaId=h.aula_id,
                autorNombre=h.autor_nombre,
                titulo=h.titulo,
                respuestas=respuestas,
                fecha=h.created_at.isoformat() if h.created_at else "",
            )
        )
    return out


@router.post(
    "/aulas/{aula_id}/foros", response_model=ForoHiloOut, status_code=status.HTTP_201_CREATED
)
def crear_hilo(
    aula_id: str,
    payload: CreateHiloRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Abre un nuevo hilo de discusión. Cualquier miembro del aula puede hacerlo."""
    _aula_con_acceso(aula_id, current_user, db)
    titulo = payload.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="El título no puede estar vacío.")
    hilo = ForoHilo(
        aula_id=aula_id,
        autor_id=current_user.id,
        autor_nombre=_nombre(current_user),
        titulo=titulo,
        created_at=datetime.now(timezone.utc),
    )
    db.add(hilo)
    db.commit()
    db.refresh(hilo)
    return ForoHiloOut(
        id=hilo.id,
        aulaId=hilo.aula_id,
        autorNombre=hilo.autor_nombre,
        titulo=hilo.titulo,
        respuestas=0,
        fecha=hilo.created_at.isoformat(),
    )


@router.get("/foros/{hilo_id}/mensajes", response_model=list[ForoMensajeOut])
def list_mensajes_hilo(
    hilo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mensajes de un hilo, del más antiguo al más reciente."""
    hilo = db.query(ForoHilo).filter(ForoHilo.id == hilo_id).first()
    if hilo is None:
        raise HTTPException(status_code=404, detail="Hilo no encontrado.")
    _aula_con_acceso(hilo.aula_id, current_user, db)
    mensajes = (
        db.query(ForoMensaje)
        .filter(ForoMensaje.hilo_id == hilo_id)
        .order_by(ForoMensaje.created_at.asc())
        .all()
    )
    return [
        ForoMensajeOut(
            id=m.id,
            hiloId=m.hilo_id,
            autorNombre=m.autor_nombre,
            texto=m.texto,
            fecha=m.created_at.isoformat() if m.created_at else "",
        )
        for m in mensajes
    ]


@router.post(
    "/foros/{hilo_id}/mensajes",
    response_model=ForoMensajeOut,
    status_code=status.HTTP_201_CREATED,
)
def responder_hilo(
    hilo_id: str,
    payload: CreateForoMensajeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Responde en un hilo del foro."""
    hilo = db.query(ForoHilo).filter(ForoHilo.id == hilo_id).first()
    if hilo is None:
        raise HTTPException(status_code=404, detail="Hilo no encontrado.")
    _aula_con_acceso(hilo.aula_id, current_user, db)
    texto = payload.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacío.")
    msg = ForoMensaje(
        hilo_id=hilo_id,
        autor_id=current_user.id,
        autor_nombre=_nombre(current_user),
        texto=texto,
        created_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return ForoMensajeOut(
        id=msg.id,
        hiloId=msg.hilo_id,
        autorNombre=msg.autor_nombre,
        texto=msg.texto,
        fecha=msg.created_at.isoformat(),
    )


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
