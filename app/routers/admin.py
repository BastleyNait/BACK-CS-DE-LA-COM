"""
Gestión de usuarios por el administrador (HU-12).
Rutas: /api/v1/admin/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import RoleEnum, User
from app.schemas.schemas import UpdateRolRequest, UsuarioAdminOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _solo_admin(user: User) -> None:
    if user.role.value != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo el administrador puede acceder.")


def _to_out(u: User) -> UsuarioAdminOut:
    return UsuarioAdminOut(
        id=u.id,
        nombres=u.nombres,
        apellidos=u.apellidos,
        email=u.email,
        role=u.role.value,
        createdAt=u.created_at.isoformat() if u.created_at else "",
    )


# ── GET /api/v1/admin/usuarios ────────────────────────────────────────────────


@router.get("/usuarios", response_model=list[UsuarioAdminOut])
def list_usuarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los usuarios del sistema ordenados por rol y apellido."""
    _solo_admin(current_user)
    usuarios = db.query(User).order_by(User.role, User.apellidos).all()
    return [_to_out(u) for u in usuarios]


# ── PUT /api/v1/admin/usuarios/{user_id}/rol ──────────────────────────────────


@router.put("/usuarios/{user_id}/rol", response_model=UsuarioAdminOut)
def update_rol(
    user_id: str,
    payload: UpdateRolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cambia el rol de un usuario. El admin no puede cambiar su propio rol."""
    _solo_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol.",
        )

    usuario = db.query(User).filter(User.id == user_id).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    usuario.role = RoleEnum(payload.role)
    db.commit()
    db.refresh(usuario)
    return _to_out(usuario)
