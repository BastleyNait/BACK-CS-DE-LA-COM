"""Asignación administrativa de prácticas y acceso de supervisores."""
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, StrictInt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.core.security import hash_password
from app.db.session import get_db
from app.models.models import Aula, Empresa, Inscripcion, Practica, PracticaEstadoEnum, Supervisor, User, RoleEnum
from app.routers.admin import _solo_admin, _auditar, _to_out
from app.routers.practicas import _to_practica_out

router = APIRouter(prefix="/admin", tags=["asignaciones"])


def lock_admin(db, actor):
    _solo_admin(actor)
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()::text), 1501)"))
    db.refresh(actor)
    _solo_admin(actor)


@router.get("/asignaciones")
def datos_asignaciones(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_admin(current_user)
    contacts = {s.empresa_id: s for s in db.query(Supervisor).all()}
    return {"versionAsignaciones": 1, "practicas": [_to_practica_out(p) for p in db.query(Practica).order_by(Practica.fecha_inicio.desc()).all()],
            "centros": [{"id": e.id, "alumnoId": e.practicante_id, "nombre": e.razon_social,
                         "supervisorId": contacts[e.id].user_id if e.id in contacts else None,
                         "contacto": (contacts[e.id].nombres + " " + contacts[e.id].apellidos) if e.id in contacts else "Sin contacto"}
                        for e in db.query(Empresa).order_by(Empresa.razon_social).all()]}


class CrearSupervisorRequest(BaseModel):
    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    solicitudId: str = Field(pattern=r"^[a-zA-Z0-9-]{16,80}$")


@router.post("/supervisores", status_code=201)
def crear_supervisor(body: CrearSupervisorRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lock_admin(db, current_user)
    key = "u-supervisor-" + sha256(body.solicitudId.encode()).hexdigest()
    existing = db.get(User, key)
    if existing:
        if (existing.email, existing.nombres, existing.apellidos, existing.role.value) != (body.email.lower(), body.nombres.strip(), body.apellidos.strip(), "SUPERVISOR"):
            raise HTTPException(409, "La solicitud ya se usó con otros datos.")
        return _to_out(existing)
    if not body.nombres.strip() or not body.apellidos.strip() or len(body.password.encode()) > 72:
        raise HTTPException(422, "Revisa nombres, apellidos y longitud de la contraseña.")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "El correo ya tiene una cuenta. Selecciónala para vincularla si es supervisor.")
    user = User(id=key, nombres=body.nombres.strip(), apellidos=body.apellidos.strip(), email=body.email.lower(), role=RoleEnum.SUPERVISOR, hashed_password=hash_password(body.password))
    db.add(user)
    _auditar(db, current_user, "ALTA_SUPERVISOR", f"Cuenta {key}; sin envío de credenciales.")
    db.commit()
    return _to_out(user)


class AsignarPracticaRequest(BaseModel):
    alumnoId: str
    aulaId: str
    empresaId: str
    horasMinimas: StrictInt = Field(ge=1, le=5000)
    motivo: str = Field(min_length=5, max_length=1000)
    solicitudId: str = Field(pattern=r"^[a-zA-Z0-9-]{16,80}$")


@router.post("/practicas", status_code=201)
def asignar_practica(body: AsignarPracticaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lock_admin(db, current_user)
    key = "pr-" + sha256(body.solicitudId.encode()).hexdigest()
    existing = db.get(Practica, key)
    if existing:
        if (existing.practicante_id, existing.aula_id, existing.empresa_id, existing.horas_minimas) != (body.alumnoId, body.aulaId, body.empresaId, body.horasMinimas):
            raise HTTPException(409, "La solicitud ya se usó con otros datos.")
        return _to_practica_out(existing)
    aula = db.query(Aula).filter(Aula.id == body.aulaId).with_for_update().first()
    alumno = db.query(User).filter(User.id == body.alumnoId).with_for_update().first()
    centro = db.query(Empresa).filter(Empresa.id == body.empresaId).with_for_update().first()
    if not aula or aula.estado.value != "ACTIVA" or not alumno or alumno.role != RoleEnum.ALUMNO:
        raise HTTPException(422, "Selecciona un alumno y un aula activa.")
    if not db.query(Inscripcion).filter(Inscripcion.aula_id == aula.id, Inscripcion.alumno_id == alumno.id).first():
        raise HTTPException(422, "Matricula primero al alumno en esta aula.")
    if not centro or centro.practicante_id != alumno.id:
        raise HTTPException(422, "Selecciona el centro registrado por este alumno.")
    if db.query(Practica).filter(Practica.practicante_id == alumno.id, Practica.estado != PracticaEstadoEnum.CERRADA).first():
        raise HTTPException(409, "El alumno ya tiene una práctica sin cerrar. Consulta su expediente.")
    practica = Practica(id=key, practicante_id=alumno.id, aula_id=aula.id, empresa_id=centro.id, periodo=aula.periodo, horas_minimas=body.horasMinimas)
    db.add(practica)
    _auditar(db, current_user, "ASIGNAR_PRACTICA", f"{key}; {alumno.id}; aula {aula.id}; meta {body.horasMinimas} h. {body.motivo.strip()}")
    db.commit()
    return _to_practica_out(practica)


class VincularSupervisorRequest(BaseModel):
    userId: str | None = None
    anterior: str | None = None
    motivo: str = Field(min_length=5, max_length=1000)


@router.put("/centros/{empresa_id}/supervisor")
def vincular_supervisor(empresa_id: str, body: VincularSupervisorRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lock_admin(db, current_user)
    centro = db.query(Empresa).filter(Empresa.id == empresa_id).with_for_update().first()
    if not centro:
        raise HTTPException(404, "Centro no disponible.")
    practices = db.query(Practica).filter(Practica.empresa_id == centro.id).order_by(Practica.id).with_for_update().all()
    contact = db.query(Supervisor).filter(Supervisor.empresa_id == centro.id).with_for_update().first()
    previous = contact.user_id if contact else None
    if previous == body.userId:
        return {"empresaId": centro.id, "userId": previous}
    if previous != body.anterior:
        raise HTTPException(409, "El vínculo cambió. Actualiza antes de guardar.")
    if any(p.estado == PracticaEstadoEnum.CERRADA for p in practices):
        raise HTTPException(409, "El centro pertenece a un expediente cerrado. No se puede cambiar su supervisor desde este circuito.")
    user = db.query(User).filter(User.id == body.userId).with_for_update().first() if body.userId else None
    if body.userId and (not user or user.role != RoleEnum.SUPERVISOR):
        raise HTTPException(422, "Selecciona una cuenta con rol de supervisor.")
    if not contact:
        if not user:
            return {"empresaId": centro.id, "userId": None}
        contact = Supervisor(empresa_id=centro.id, nombres=user.nombres, apellidos=user.apellidos, email=user.email)
        db.add(contact)
    contact.user_id = body.userId
    if user:
        contact.nombres, contact.apellidos, contact.email = user.nombres, user.apellidos, user.email
    _auditar(db, current_user, "VINCULAR_SUPERVISOR", f"Centro {centro.id}; {previous} → {body.userId}. {body.motivo.strip()}")
    db.commit()
    return {"empresaId": centro.id, "userId": body.userId}
