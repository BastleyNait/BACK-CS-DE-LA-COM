"""
Gestión de aulas / clases / prácticas (HU-4).
Rutas: /api/v1/aulas/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Aula, AulaEstadoEnum, User
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
    else:  # ADMIN
        aulas = db.query(Aula).order_by(Aula.created_at.desc()).all()

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
    if current_user.role.value == "ALUMNO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para crear clases.",
        )

    codigo = body.codigo.upper()
    if db.query(Aula).filter(Aula.codigo == codigo).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una clase con el código {codigo}.",
        )

    aula = Aula(
        nombre=body.nombre,
        codigo=codigo,
        descripcion=body.descripcion,
        periodo=body.periodo,
        profesor_id=current_user.id,
        estado=AulaEstadoEnum.ACTIVA,
        inscritos=0,
    )
    db.add(aula)
    db.commit()
    db.refresh(aula)
    return _aula_to_out(aula)
