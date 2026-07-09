"""
Registro de empresa/centro de prácticas (HU-13) y su supervisor externo (HU-19).
Solo el propio practicante gestiona sus datos.
Rutas: /api/v1/empresa/*
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Empresa, Supervisor, User
from app.schemas.schemas import (
    CreateEmpresaRequest,
    CreateSupervisorRequest,
    EmpresaOut,
    SupervisorOut,
)

router = APIRouter(prefix="/empresa", tags=["empresa"])


def _to_empresa_out(e: Empresa) -> EmpresaOut:
    return EmpresaOut(
        id=e.id,
        practicanteId=e.practicante_id,
        razonSocial=e.razon_social,
        ruc=e.ruc,
        direccion=e.direccion,
        sector=e.sector,
        telefono=e.telefono,
        email=e.email,
        fechaRegistro=e.created_at.isoformat() if e.created_at else "",
    )


def _to_supervisor_out(s: Supervisor) -> SupervisorOut:
    return SupervisorOut(
        id=s.id,
        empresaId=s.empresa_id,
        nombres=s.nombres,
        apellidos=s.apellidos,
        cargo=s.cargo,
        email=s.email,
        telefono=s.telefono,
    )


# ── GET /api/v1/empresa/mine ──────────────────────────────────────────────────


@router.get("/mine", response_model=Optional[EmpresaOut])
def get_mine(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Empresa registrada por el practicante autenticado, o null si no existe."""
    empresa = (
        db.query(Empresa).filter(Empresa.practicante_id == current_user.id).first()
    )
    return _to_empresa_out(empresa) if empresa else None


# ── GET /api/v1/empresa/{empresa_id}/supervisor ───────────────────────────────


@router.get("/{empresa_id}/supervisor", response_model=Optional[SupervisorOut])
def get_supervisor(
    empresa_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supervisor registrado para la empresa indicada, o null si no existe."""
    supervisor = (
        db.query(Supervisor).filter(Supervisor.empresa_id == empresa_id).first()
    )
    return _to_supervisor_out(supervisor) if supervisor else None


# ── POST /api/v1/empresa ──────────────────────────────────────────────────────


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def register_empresa(
    payload: CreateEmpresaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra la empresa/centro de prácticas del practicante (HU-13)."""
    if current_user.role.value != "ALUMNO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el practicante puede registrar su empresa.",
        )
    existe = (
        db.query(Empresa).filter(Empresa.practicante_id == current_user.id).first()
    )
    if existe is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya registraste una empresa para tus prácticas.",
        )

    empresa = Empresa(
        practicante_id=current_user.id,
        razon_social=payload.razonSocial,
        ruc=payload.ruc,
        direccion=payload.direccion,
        sector=payload.sector,
        telefono=payload.telefono,
        email=payload.email,
    )
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return _to_empresa_out(empresa)


# ── POST /api/v1/empresa/{empresa_id}/supervisor ──────────────────────────────


@router.post(
    "/{empresa_id}/supervisor",
    response_model=SupervisorOut,
    status_code=status.HTTP_201_CREATED,
)
def register_supervisor(
    empresa_id: str,
    payload: CreateSupervisorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra al supervisor externo asignado en la empresa (HU-19)."""
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    if empresa.practicante_id != current_user.id and current_user.role.value == "ALUMNO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el practicante dueño puede registrar el supervisor.",
        )
    if db.query(Supervisor).filter(Supervisor.empresa_id == empresa_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un supervisor registrado para esta empresa.",
        )

    supervisor = Supervisor(
        empresa_id=empresa_id,
        nombres=payload.nombres,
        apellidos=payload.apellidos,
        cargo=payload.cargo,
        email=payload.email,
        telefono=payload.telefono,
    )
    db.add(supervisor)
    db.commit()
    db.refresh(supervisor)
    return _to_supervisor_out(supervisor)
