"""
Gestión de metas por practicante (HU-20/21): el asesor define objetivos
cuantitativos (artículos, notas periodísticas, notas de prensa, horas
trabajadas) y el practicante visualiza su avance real.
Rutas: /api/v1/metas/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Aula, Meta, MetaTipoEnum, Practica, User
from app.schemas.schemas import CreateMetaRequest, MetaOut, RegistrarAvanceMetaRequest

router = APIRouter(prefix="/metas", tags=["metas"])


def _to_out(m: Meta) -> MetaOut:
    """Para metas de tipo HORAS, el avance real es siempre horas_acumuladas de
    la práctica (la misma bitácora de HU-14), no un contador propio."""
    cantidad_alcanzada = (
        m.practica.horas_acumuladas if m.tipo == MetaTipoEnum.HORAS else m.cantidad_alcanzada
    )
    return MetaOut(
        id=m.id,
        practicaId=m.practica_id,
        practicanteId=m.practica.practicante_id,
        practicanteNombre=(
            f"{m.practica.practicante.nombres} {m.practica.practicante.apellidos}"
        ),
        tipo=m.tipo.value,
        cantidadObjetivo=m.cantidad_objetivo,
        cantidadAlcanzada=cantidad_alcanzada,
        descripcion=m.descripcion,
        creadoPor=m.creado_por,
        fechaCreacion=m.created_at.isoformat() if m.created_at else "",
    )


def _metas_visibles(db: Session, user: User) -> list[Meta]:
    if user.role.value == "ALUMNO":
        practica_ids = [
            p.id for p in db.query(Practica).filter(Practica.practicante_id == user.id)
        ]
    elif user.role.value == "PROFESOR":
        aula_ids = [a.id for a in db.query(Aula).filter(Aula.profesor_id == user.id)]
        practica_ids = [
            p.id for p in db.query(Practica).filter(Practica.aula_id.in_(aula_ids))
        ]
    elif user.role.value == "ADMIN":
        return db.query(Meta).all()
    else:
        return []
    if not practica_ids:
        return []
    return db.query(Meta).filter(Meta.practica_id.in_(practica_ids)).all()


# ── GET /api/v1/metas ──────────────────────────────────────────────────────────


@router.get("", response_model=list[MetaOut])
def list_metas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Metas visibles para el usuario según su rol."""
    return [_to_out(m) for m in _metas_visibles(db, current_user)]


# ── GET /api/v1/metas/practicante/{practicante_id} ────────────────────────────


@router.get("/practicante/{practicante_id}", response_model=list[MetaOut])
def list_by_practicante(
    practicante_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Metas de un practicante específico (para la vista de gestión)."""
    practica_ids = [
        p.id
        for p in db.query(Practica).filter(Practica.practicante_id == practicante_id)
    ]
    if not practica_ids:
        return []
    metas = db.query(Meta).filter(Meta.practica_id.in_(practica_ids)).all()
    return [_to_out(m) for m in metas]


# ── POST /api/v1/metas/practica/{practica_id} ─────────────────────────────────


@router.post(
    "/practica/{practica_id}", response_model=MetaOut, status_code=status.HTTP_201_CREATED
)
def create_meta(
    practica_id: str,
    payload: CreateMetaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Define una nueva meta para el ciclo de prácticas indicado."""
    if current_user.role.value == "ALUMNO":
        raise HTTPException(
            status_code=403, detail="Solo un asesor o administrador puede definir metas."
        )
    practica = db.query(Practica).filter(Practica.id == practica_id).first()
    if practica is None:
        raise HTTPException(
            status_code=404, detail="No se encontró la práctica del practicante."
        )
    if payload.cantidadObjetivo <= 0:
        raise HTTPException(
            status_code=400, detail="La cantidad objetivo debe ser mayor a 0."
        )

    meta = Meta(
        practica_id=practica_id,
        tipo=MetaTipoEnum(payload.tipo),
        cantidad_objetivo=payload.cantidadObjetivo,
        cantidad_alcanzada=0,
        descripcion=(payload.descripcion or "").strip() or None,
        creado_por=f"{current_user.nombres} {current_user.apellidos}",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return _to_out(meta)


# ── PUT /api/v1/metas/{meta_id}/avance ────────────────────────────────────────


@router.put("/{meta_id}/avance", response_model=MetaOut)
def registrar_avance(
    meta_id: str,
    payload: RegistrarAvanceMetaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra avance real (cantidad producida) sobre una meta existente."""
    if current_user.role.value == "ALUMNO":
        raise HTTPException(
            status_code=403,
            detail="Solo un asesor o administrador puede registrar el avance.",
        )
    meta = db.query(Meta).filter(Meta.id == meta_id).first()
    if meta is None:
        raise HTTPException(status_code=404, detail="No se encontró la meta.")
    if meta.tipo == MetaTipoEnum.HORAS:
        raise HTTPException(
            status_code=409,
            detail=(
                "El avance de horas trabajadas se calcula automáticamente desde "
                "la bitácora de horas."
            ),
        )
    if payload.cantidad <= 0:
        raise HTTPException(status_code=400, detail="La cantidad debe ser mayor a 0.")

    meta.cantidad_alcanzada += payload.cantidad
    db.commit()
    db.refresh(meta)
    return _to_out(meta)
