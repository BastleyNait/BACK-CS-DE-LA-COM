"""Permisos por recurso y cómputo transaccional de horas aprobadas."""
from fastapi import HTTPException
from sqlalchemy import func, select
from app.models.models import Aula, Practica, PracticaEstadoEnum, RegistroHoras, RegistroHorasEstadoEnum, Supervisor


def visible_practices(db, user):
    query = db.query(Practica)
    role = user.role.value
    if role == "ALUMNO":
        return query.filter(Practica.practicante_id == user.id)
    if role == "PROFESOR":
        return query.filter(Practica.aula_id.in_(select(Aula.id).where(Aula.profesor_id == user.id)))
    if role == "SUPERVISOR":
        return query.filter(Practica.empresa_id.in_(select(Supervisor.empresa_id).where(Supervisor.user_id == user.id)))
    if role == "ADMIN":
        return query
    raise HTTPException(403, "Acceso restringido.")


def require_practice(db, user, practice_id, lock=False):
    query = visible_practices(db, user).filter(Practica.id == practice_id)
    if lock:
        query = query.populate_existing().with_for_update()
    practice = query.first()
    if practice is None:
        raise HTTPException(404, "La práctica no está disponible para tu cuenta.")
    return practice


def sync_hours(db, practice):
    # Todas las escrituras toman primero el bloqueo de la práctica.
    db.flush()
    practice.horas_acumuladas = db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(
        RegistroHoras.practica_id == practice.id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO,
    ).scalar()
    if practice.estado != PracticaEstadoEnum.CERRADA:
        practice.estado = (PracticaEstadoEnum.LISTA_PARA_CIERRE if practice.horas_acumuladas >= practice.horas_minimas else PracticaEstadoEnum.EN_CURSO)
