"""
Gestión de aulas / clases / prácticas (HU-4).
Rutas: /api/v1/aulas/*
"""

import hashlib
import uuid
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Auditoria, Aula, AulaEstadoEnum, RoleEnum, User
from app.schemas.schemas import AulaOut, CreateAulaRequest

router = APIRouter(prefix="/aulas", tags=["aulas"])


def _aula_to_out(aula: Aula) -> AulaOut:
    """Convierte el modelo ORM al schema de salida que espera el frontend."""
    return AulaOut(
        id=aula.id,
        nombre=aula.nombre,
        codigo=aula.codigo,
        descripcion=aula.descripcion,
        periodo=aula.periodo,
        profesorId=aula.profesor_id,
        profesorNombre=f"{aula.profesor.nombres} {aula.profesor.apellidos}",
        estado=aula.estado.value,
        inscritos=aula.inscritos,
        createdAt=aula.created_at.isoformat() if aula.created_at else "",
    )


# ── GET /api/v1/aulas ──────────────────────────────────────────────────────────


@router.get("", response_model=list[AulaOut])
def list_aulas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista las aulas visibles según rol (RBAC).
    - PROFESOR: solo sus propias aulas.
    - ADMIN: todas las aulas.
    - ALUMNO: todas las aulas activas.
    Equivale al mock: aulaService.list()
    """
    if current_user.role.value == "PROFESOR":
        aulas = (
            db.query(Aula)
            .filter(Aula.profesor_id == current_user.id)
            .order_by(Aula.created_at.desc())
            .all()
        )
    elif current_user.role.value == "ALUMNO":
        aulas = (
            db.query(Aula)
            .filter(Aula.estado == AulaEstadoEnum.ACTIVA)
            .order_by(Aula.created_at.desc())
            .all()
        )
    elif current_user.role.value == "ADMIN":
        aulas = db.query(Aula).order_by(Aula.created_at.desc()).all()

    else:
        raise HTTPException(403, "Sección para miembros del aula.")

    return [_aula_to_out(a) for a in aulas]


# ── POST /api/v1/aulas ─────────────────────────────────────────────────────────


@router.post("", response_model=AulaOut, status_code=status.HTTP_201_CREATED)
def create_aula(
    body: CreateAulaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Crea una nueva clase/práctica. Solo ADMIN y PROFESOR.
    Equivale al mock: aulaService.create()
    Errores: 403 si es ALUMNO, 409 si el código ya existe.
    """
    if current_user.role.value not in {"ADMIN", "PROFESOR"}:
        raise HTTPException(403, "Solo docencia o administración crea aulas.")
    profesor_id = body.profesorId or (current_user.id if current_user.role.value == "PROFESOR" else None)
    if not profesor_id:
        raise HTTPException(422, "Selecciona un docente responsable.")
    if current_user.role.value == "PROFESOR" and profesor_id != current_user.id:
        raise HTTPException(403, "Solo puedes crear aulas a tu cargo.")
    profesor = db.query(User).filter(User.id == profesor_id).populate_existing().with_for_update().first()
    if not profesor or profesor.role != RoleEnum.PROFESOR:
        raise HTTPException(422, "El responsable debe ser docente.")
    codigo = body.codigo.upper()
    record_id = "a-" + (hashlib.sha256(f"{current_user.id}:{body.solicitudId}".encode()).hexdigest() if body.solicitudId else uuid.uuid4().hex)
    def same(a):
        return (a.nombre, a.codigo, a.descripcion, a.periodo, a.profesor_id) == (body.nombre, codigo, body.descripcion, body.periodo, profesor_id)
    existing = db.get(Aula, record_id)
    if existing:
        if not same(existing):
            raise HTTPException(409, "La solicitud ya se utilizó con otros datos.")
        return _aula_to_out(existing)
    if db.query(Aula).filter(Aula.codigo == codigo).first():
        raise HTTPException(409, "El código de aula ya está en uso.")
    aula = Aula(id=record_id, nombre=body.nombre, codigo=codigo, descripcion=body.descripcion, periodo=body.periodo,
                profesor_id=profesor_id, estado=AulaEstadoEnum.ACTIVA, inscritos=0)
    db.add(aula)
    db.add(Auditoria(user_id=current_user.id, user_nombre=f"{current_user.nombres} {current_user.apellidos}",
                     accion="AULA_CREADA", detalle=f"{body.nombre} ({codigo}), periodo {body.periodo}; docente {profesor.nombres} {profesor.apellidos}"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(Aula, record_id)
        if existing and same(existing):
            return _aula_to_out(existing)
        raise HTTPException(409, "El código o la solicitud ya está en uso.") from None
    return _aula_to_out(aula)
