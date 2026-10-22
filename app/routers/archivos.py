"""Documentos privados, limitados y persistentes en la base autorizada."""
import io
from pathlib import PurePosixPath
from hashlib import sha256
import re
import uuid
import zipfile
from urllib.parse import quote
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Archivo, Aula, ContenidoArchivo, Entrega, Inscripcion, Practica, PracticaEstadoEnum, User, VersionEntrega
from app.schemas.schemas import ArchivoOut

router = APIRouter(tags=["archivos"])
MAX_FILE_SIZE = 10 * 1024 * 1024
USER_QUOTA = 100 * 1024 * 1024
MIMES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".zip": "application/zip"}


def _verificar_acceso(aula_id, current_user, db, write=False):
    aula = db.query(Aula).filter(Aula.id == aula_id).populate_existing().with_for_update().first() if write else db.get(Aula, aula_id)
    if not aula:
        raise HTTPException(404, "Aula no encontrada.")
    role = current_user.role.value
    if not (role == "ADMIN" or role == "PROFESOR" and aula.profesor_id == current_user.id or
            role == "ALUMNO" and db.query(Inscripcion).filter(Inscripcion.alumno_id == current_user.id, Inscripcion.aula_id == aula_id).first()):
        raise HTTPException(403, "No tienes acceso a esta aula.")
    if write and aula.estado.value != "ACTIVA":
        raise HTTPException(409, "El aula está concluida.")
    if write and role == "ALUMNO" and db.query(Practica).filter(Practica.aula_id == aula_id, Practica.practicante_id == current_user.id, Practica.estado == PracticaEstadoEnum.CERRADA).first():
        raise HTTPException(409, "La práctica está cerrada.")
    return aula


def visible_files(db, aula_id, user):
    query = db.query(Archivo).filter(Archivo.aula_id == aula_id)
    if user.role.value == "ALUMNO":
        query = query.filter(or_(Archivo.subido_por_id == user.id, Archivo.id.in_(select(ContenidoArchivo.archivo_id).where(ContenidoArchivo.material == 1))))
    return query


def _to_out(arch):
    return ArchivoOut(id=arch.id, aulaId=arch.aula_id, subidoPorId=arch.subido_por_id,
        subidoPorNombre=f"{arch.subido_por.nombres} {arch.subido_por.apellidos}", nombreOriginal=arch.nombre_original,
        tipoMime=arch.tipo_mime, tamanio=arch.tamanio, createdAt=arch.created_at.isoformat() if arch.created_at else "")


def validate_document(name, supplied_mime, data):
    ext = PurePosixPath(name).suffix.lower()
    if not data or len(data) > MAX_FILE_SIZE:
        raise HTTPException(413, "El documento debe tener contenido y no superar 10 MB.")
    if ext not in MIMES:
        raise HTTPException(422, "Solo se admiten PDF, DOCX y ZIP.")
    expected = MIMES[ext]
    allowed = {expected, "application/octet-stream", ""}
    if ext == ".zip": allowed.add("application/x-zip-compressed")
    if supplied_mime not in allowed:
        raise HTTPException(422, "El tipo declarado no coincide con el documento.")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise HTTPException(422, "El contenido no corresponde a un PDF completo.")
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000 or sum(i.file_size for i in entries) > 50 * 1024 * 1024:
                    raise ValueError()
                for i in entries:
                    path = PurePosixPath(i.filename.replace("\\", "/"))
                    if i.flag_bits & 1 or path.is_absolute() or ".." in path.parts or ":" in i.filename or (i.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError()
                    if i.file_size > max(i.compress_size, 1) * 200 or path.suffix.lower() in {".exe", ".bat", ".cmd", ".com", ".dll", ".ps1", ".js", ".html", ".htm", ".scr", ".vbs"}:
                        raise ValueError()
                    if path.name.lower() == "vbaproject.bin": raise ValueError()
                if ext == ".docx" and not {"[Content_Types].xml", "word/document.xml"}.issubset(archive.namelist()):
                    raise ValueError()
                if archive.testzip() is not None: raise ValueError()
        except (zipfile.BadZipFile, ValueError, RuntimeError, NotImplementedError):
            raise HTTPException(422, "El archivo comprimido es inválido, está cifrado o contiene elementos no permitidos.") from None
    return expected


@router.get("/aulas/{aula_id}/archivos", response_model=list[ArchivoOut])
def list_archivos(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _verificar_acceso(aula_id, current_user, db)
    return [_to_out(a) for a in visible_files(db, aula_id, current_user).order_by(Archivo.created_at.desc()).all()]


@router.post("/aulas/{aula_id}/archivos", response_model=ArchivoOut, status_code=201)
def upload_archivo(aula_id: str, file: UploadFile = File(...), solicitudId: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _verificar_acceso(aula_id, current_user, db, write=True)
    db.query(User).filter(User.id == current_user.id).with_for_update().one()
    if not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", solicitudId):
        raise HTTPException(422, "Identificador de carga inválido.")
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not name or len(name) > 255 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "Nombre de documento inválido.")
    data = file.file.read(MAX_FILE_SIZE + 1)
    mime = validate_document(name, file.content_type or "", data)
    digest = sha256(data).hexdigest()
    key = "arc-" + sha256(f"{current_user.id}:{solicitudId}".encode()).hexdigest()
    existing = db.get(Archivo, key)
    if existing:
        content = db.get(ContenidoArchivo, key)
        if (existing.aula_id, existing.nombre_original, content.sha256 if content else None) != (aula_id, name, digest):
            raise HTTPException(409, "La solicitud de carga ya se usó con otro documento.")
        return _to_out(existing)
    used = db.query(func.coalesce(func.sum(Archivo.tamanio), 0)).filter(Archivo.subido_por_id == current_user.id).scalar()
    if used + len(data) > USER_QUOTA:
        raise HTTPException(413, "Alcanzaste el límite de 100 MB de documentos. Elimina cargas que no hayas entregado.")
    arch = Archivo(id=key, aula_id=aula_id, subido_por_id=current_user.id, nombre_original=name,
                   nombre_guardado=uuid.uuid4().hex, tipo_mime=mime, tamanio=len(data))
    db.add(arch); db.flush()
    db.add(ContenidoArchivo(archivo_id=key, datos=data, sha256=digest, material=1 if current_user.role.value in {"ADMIN", "PROFESOR"} else 0))
    db.commit()
    return _to_out(arch)


@router.get("/aulas/{aula_id}/archivos/{archivo_id}/descargar")
def descargar_archivo(aula_id: str, archivo_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _verificar_acceso(aula_id, current_user, db)
    arch = visible_files(db, aula_id, current_user).filter(Archivo.id == archivo_id).first()
    if not arch: raise HTTPException(404, "Documento no disponible.")
    content = db.get(ContenidoArchivo, archivo_id)
    if not content: raise HTTPException(404, "El documento antiguo no está en el almacenamiento persistente. Solicita una nueva carga.")
    return Response(content=content.datos, media_type=arch.tipo_mime, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(arch.nombre_original), "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/aulas/{aula_id}/archivos/{archivo_id}", status_code=204)
def eliminar_archivo(aula_id: str, archivo_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _verificar_acceso(aula_id, current_user, db, write=True)
    arch = db.query(Archivo).filter(Archivo.id == archivo_id, Archivo.aula_id == aula_id, Archivo.subido_por_id == current_user.id).with_for_update().first()
    if not arch: raise HTTPException(404, "Carga propia no disponible.")
    if db.query(Entrega).filter(Entrega.archivo_id == archivo_id).first() or db.query(VersionEntrega).filter(VersionEntrega.archivo_id == archivo_id).first():
        raise HTTPException(409, "El documento pertenece a una entrega o a su historial y debe conservarse.")
    content = db.get(ContenidoArchivo, archivo_id)
    if content: db.delete(content)
    db.flush(); db.delete(arch); db.commit()
    return Response(status_code=204)
