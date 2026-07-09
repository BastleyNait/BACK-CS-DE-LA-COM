"""
Gestión de archivos del SSP (HU-07 upload / HU-08 download).
Rutas: /api/v1/aulas/{aula_id}/archivos/*
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Archivo, Aula, Inscripcion, User
from app.schemas.schemas import ArchivoOut

router = APIRouter(tags=["archivos"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

UPLOAD_BASE = Path(settings.UPLOAD_DIR).resolve()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _verificar_acceso(aula_id: str, current_user: User, db: Session) -> Aula:
    """Devuelve el aula si el usuario tiene acceso; lanza 403/404 si no."""
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if aula is None:
        raise HTTPException(status_code=404, detail="Aula no encontrada.")

    role = current_user.role.value
    if role == "ADMIN":
        return aula
    if role == "PROFESOR" and aula.profesor_id == current_user.id:
        return aula
    if role == "ALUMNO":
        ins = (
            db.query(Inscripcion)
            .filter(
                Inscripcion.alumno_id == current_user.id,
                Inscripcion.aula_id == aula_id,
            )
            .first()
        )
        if ins:
            return aula

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a esta aula.",
    )


def _to_out(arch: Archivo) -> ArchivoOut:
    u = arch.subido_por
    return ArchivoOut(
        id=arch.id,
        aulaId=arch.aula_id,
        subidoPorId=arch.subido_por_id,
        subidoPorNombre=f"{u.nombres} {u.apellidos}",
        nombreOriginal=arch.nombre_original,
        tipoMime=arch.tipo_mime,
        tamanio=arch.tamanio,
        createdAt=arch.created_at.isoformat() if arch.created_at else "",
    )


# ── GET /api/v1/aulas/{aula_id}/archivos ─────────────────────────────────────


@router.get("/aulas/{aula_id}/archivos", response_model=list[ArchivoOut])
def list_archivos(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los archivos de un aula, del más reciente al más antiguo."""
    _verificar_acceso(aula_id, current_user, db)

    archivos = (
        db.query(Archivo)
        .filter(Archivo.aula_id == aula_id)
        .order_by(Archivo.created_at.desc())
        .all()
    )
    return [_to_out(a) for a in archivos]


# ── POST /api/v1/aulas/{aula_id}/archivos ────────────────────────────────────


@router.post(
    "/aulas/{aula_id}/archivos",
    response_model=ArchivoOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_archivo(
    aula_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sube un archivo al aula (max 20 MB). Devuelve los metadatos del archivo."""
    _verificar_acceso(aula_id, current_user, db)

    contenido = file.file.read()
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera el límite de 20 MB.",
        )

    ext = Path(file.filename or "archivo").suffix
    nombre_guardado = f"{uuid.uuid4().hex}{ext}"

    ruta_dir = UPLOAD_BASE / aula_id
    ruta_dir.mkdir(parents=True, exist_ok=True)
    (ruta_dir / nombre_guardado).write_bytes(contenido)

    arch = Archivo(
        aula_id=aula_id,
        subido_por_id=current_user.id,
        nombre_original=file.filename or nombre_guardado,
        nombre_guardado=nombre_guardado,
        tipo_mime=file.content_type or "application/octet-stream",
        tamanio=len(contenido),
        created_at=datetime.now(timezone.utc),
    )
    db.add(arch)
    db.commit()
    db.refresh(arch)
    return _to_out(arch)


# ── GET /api/v1/aulas/{aula_id}/archivos/{archivo_id}/descargar ──────────────


@router.get("/aulas/{aula_id}/archivos/{archivo_id}/descargar")
def descargar_archivo(
    aula_id: str,
    archivo_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Descarga un archivo con Content-Disposition: attachment."""
    _verificar_acceso(aula_id, current_user, db)

    arch = (
        db.query(Archivo)
        .filter(Archivo.id == archivo_id, Archivo.aula_id == aula_id)
        .first()
    )
    if arch is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    ruta = UPLOAD_BASE / aula_id / arch.nombre_guardado
    if not ruta.exists():
        raise HTTPException(
            status_code=404, detail="El archivo no existe en el servidor."
        )

    return FileResponse(
        path=str(ruta),
        filename=arch.nombre_original,
        media_type=arch.tipo_mime,
    )
