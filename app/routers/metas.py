"""Metas por práctica: consulta por alcance y seguimiento docente auditado."""
import hashlib
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload
from app.core.deps import get_current_user
from app.core.practice_access import require_practice, visible_practices
from app.db.session import get_db
from app.models.models import Auditoria, Meta, MetaTipoEnum, Practica, PracticaEstadoEnum, RegistroHorasEstadoEnum, User
from app.schemas.schemas import CreateMetaRequest, MetaOut, RegistrarAvanceMetaRequest, EstablecerAvanceMetaRequest

router = APIRouter(prefix="/metas", tags=["metas"])


def _to_out(m):
    alcanzada = sum(r.horas for r in m.practica.registros_horas if r.estado_validacion == RegistroHorasEstadoEnum.VALIDADO) if m.tipo == MetaTipoEnum.HORAS else m.cantidad_alcanzada
    return MetaOut(id=m.id, practicaId=m.practica_id, practicanteId=m.practica.practicante_id,
        practicanteNombre=f"{m.practica.practicante.nombres} {m.practica.practicante.apellidos}",
        tipo=m.tipo.value, cantidadObjetivo=m.cantidad_objetivo, cantidadAlcanzada=alcanzada,
        descripcion=m.descripcion, creadoPor=m.creado_por, fechaCreacion=m.created_at.isoformat())


def _metas_visibles(db, user):
    return db.query(Meta).filter(Meta.practica_id.in_(visible_practices(db, user).with_entities(Practica.id).statement)).options(
        selectinload(Meta.practica).selectinload(Practica.practicante),
        selectinload(Meta.practica).selectinload(Practica.registros_horas))


def _editor(db, user, practica_id):
    if user.role.value not in {"PROFESOR", "ADMIN"}:
        raise HTTPException(403, "Solo el docente responsable o administración gestiona metas.")
    return require_practice(db, user, practica_id, lock=True)


def _open(practica):
    if practica.estado == PracticaEstadoEnum.CERRADA:
        raise HTTPException(409, "La práctica está cerrada.")


def _audit(db, user, action, detail):
    db.add(Auditoria(user_id=user.id, user_nombre=f"{user.nombres} {user.apellidos}", accion=action, detalle=detail))


@router.get("/capacidades")
def capacidades(current_user: User = Depends(get_current_user)):
    return {"versionMetas": 1, "avanceTotal": True}


@router.get("", response_model=list[MetaOut])
def list_metas(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_to_out(m) for m in _metas_visibles(db, current_user).order_by(Meta.created_at.desc(), Meta.id).all()]


@router.get("/practicante/{practicante_id}", response_model=list[MetaOut])
def list_by_practicante(practicante_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_to_out(m) for m in _metas_visibles(db, current_user).filter(Meta.practica_id.in_(db.query(Practica.id).filter(Practica.practicante_id == practicante_id).statement)).all()]


@router.get("/practica/{practica_id}", response_model=list[MetaOut])
def list_by_practica(practica_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_practice(db, current_user, practica_id)
    return [_to_out(m) for m in _metas_visibles(db, current_user).filter(Meta.practica_id == practica_id).order_by(Meta.created_at.desc(), Meta.id).all()]


@router.post("/practica/{practica_id}", response_model=MetaOut, status_code=201)
def create_meta(practica_id: str, payload: CreateMetaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    practica = _editor(db, current_user, practica_id)
    key = hashlib.sha256(f"{current_user.id}:{practica_id}:{payload.solicitudId}".encode()).hexdigest() if payload.solicitudId else uuid.uuid4().hex
    existing = db.get(Meta, "m-" + key)
    if existing:
        if (existing.tipo.value, existing.cantidad_objetivo, existing.descripcion) != (payload.tipo, payload.cantidadObjetivo, payload.descripcion):
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _to_out(existing)
    _open(practica)
    meta = Meta(id="m-" + key, practica_id=practica_id, tipo=MetaTipoEnum(payload.tipo), cantidad_objetivo=payload.cantidadObjetivo,
                cantidad_alcanzada=0, descripcion=payload.descripcion, creado_por=f"{current_user.nombres} {current_user.apellidos}")
    db.add(meta)
    _audit(db, current_user, "META_CREADA", f"Meta {meta.id} para {practica.practicante.nombres}: {payload.tipo}, objetivo {payload.cantidadObjetivo}. {payload.descripcion or ''}")
    db.commit()
    return _to_out(meta)


@router.put("/{meta_id}/avance-total", response_model=MetaOut)
def establecer_avance(meta_id: str, payload: EstablecerAvanceMetaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    practica_id = db.query(Meta.practica_id).filter(Meta.id == meta_id).scalar()
    if practica_id is None:
        raise HTTPException(404, "Meta no disponible.")
    practica = _editor(db, current_user, practica_id)
    meta = db.query(Meta).filter(Meta.id == meta_id).populate_existing().with_for_update().one()
    if meta.tipo == MetaTipoEnum.HORAS:
        raise HTTPException(409, "Las metas de horas se calculan desde las horas validadas.")
    if meta.cantidad_alcanzada == payload.cantidad:
        return _to_out(meta)
    _open(practica)
    if meta.cantidad_alcanzada != payload.anterior:
        raise HTTPException(409, "El avance cambió. Consulta el total actualizado antes de guardar.")
    anterior = meta.cantidad_alcanzada
    meta.cantidad_alcanzada = payload.cantidad
    _audit(db, current_user, "META_AVANCE", f"Meta {meta.id}: {anterior} → {payload.cantidad}. Producción revisada: {payload.motivo}")
    db.commit()
    return _to_out(meta)


@router.put("/{meta_id}/avance", response_model=MetaOut)
def registrar_avance(meta_id: str, payload: RegistrarAvanceMetaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    practica_id = db.query(Meta.practica_id).filter(Meta.id == meta_id).scalar()
    if practica_id is None:
        raise HTTPException(404, "Meta no disponible.")
    _editor(db, current_user, practica_id)
    raise HTTPException(409, "Usa avance-total con el valor anterior para evitar duplicar producción al reintentar.")
