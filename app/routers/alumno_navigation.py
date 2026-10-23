"""Lecturas ligeras para la navegación del alumno; sin cambios de esquema."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, func, case, exists
from sqlalchemy.orm import Session, joinedload
from app.core.deps import get_current_user
from app.core.hours import to_record
from app.core.practice_access import require_practice
from app.db.session import get_db
from app.models.models import (User, Practica, RegistroHoras, RegistroHorasEstadoEnum,
    PracticaEstadoEnum, Inscripcion, Aula, Tarea, Entrega)

router = APIRouter(prefix="/alumno", tags=["alumno"])


def student(user):
    if user.role.value != "ALUMNO":
        raise HTTPException(403, "Esta experiencia está disponible para alumnos.")


def summary(db, practice_id):
    rows = db.query(RegistroHoras.estado_validacion, func.count(RegistroHoras.id),
        func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(
        RegistroHoras.practica_id == practice_id).group_by(RegistroHoras.estado_validacion).all()
    result = {key: {"registros": 0, "horas": 0} for key in ["PENDIENTE", "VALIDADO", "RECHAZADO"]}
    for state, count, hours in rows:
        result[state.value] = {"registros": count, "horas": hours}
    return result


def practice_out(p, totals):
    approved = totals["VALIDADO"]["horas"]
    state = p.estado.value if p.estado == PracticaEstadoEnum.CERRADA else (
        "LISTA_PARA_CIERRE" if approved >= p.horas_minimas else "EN_CURSO")
    return {"id": p.id, "practicanteId": p.practicante_id,
        "practicanteNombre": f"{p.practicante.nombres} {p.practicante.apellidos}",
        "aulaNombre": p.aula.nombre, "periodo": p.periodo, "estado": state,
        "horasMinimas": p.horas_minimas, "horasAcumuladas": approved, "correcciones": True}


@router.get("/inicio")
def inicio(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student(current_user)
    enrolled = db.query(Inscripcion).options(joinedload(Inscripcion.aula).joinedload(Aula.profesor)).filter(
        Inscripcion.alumno_id == current_user.id).all()
    aulas = [{"id": i.aula.id, "nombre": i.aula.nombre,
        "profesorNombre": f"{i.aula.profesor.nombres} {i.aula.profesor.apellidos}",
        "ciclo": i.aula.periodo, "estado": i.aula.estado.value} for i in enrolled]
    aulas.sort(key=lambda a: (a["estado"] != "ACTIVA", a["nombre"], a["id"]))
    p = db.query(Practica).filter(Practica.practicante_id == current_user.id).order_by(
        case((Practica.estado == PracticaEstadoEnum.CERRADA, 1), else_=0),
        Practica.fecha_inicio.desc(), Practica.id.desc()).first()
    totals = summary(db, p.id) if p else None
    correction = db.query(RegistroHoras).filter(RegistroHoras.practica_id == p.id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.RECHAZADO).order_by(
        RegistroHoras.fecha.desc(), RegistroHoras.id.desc()).first() if p and p.estado != PracticaEstadoEnum.CERRADA else None
    next_task = db.query(Tarea).join(Aula, Aula.id == Tarea.aula_id).filter(
        Tarea.aula_id.in_([a["id"] for a in aulas if a["estado"] == "ACTIVA"]),
        ~exists().where(and_(Entrega.tarea_id == Tarea.id, Entrega.alumno_id == current_user.id)),
    ).order_by(Tarea.fecha_limite.asc().nullslast(), Tarea.id.asc()).first()
    task = {"id": next_task.id, "aulaId": next_task.aula_id, "titulo": next_task.titulo,
        "aulaNombre": next_task.aula.nombre, "fechaLimite": next_task.fecha_limite.isoformat() if next_task.fecha_limite else None} if next_task else None
    return {"aulas": aulas, "practica": practice_out(p, totals) if p else None,
        "resumen": totals, "porCorregir": to_record(correction) if correction else None, "proximaTarea": task}


@router.get("/practicas/{practica_id}/bitacora")
def bitacora(practica_id: str, limite: int = Query(20, ge=1, le=50),
    estado: Literal["PENDIENTE", "VALIDADO", "RECHAZADO"] | None = None,
    cursor: str | None = Query(None, max_length=400),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student(current_user)
    p = require_practice(db, current_user, practica_id)
    totals = summary(db, p.id)
    query = db.query(RegistroHoras).filter(RegistroHoras.practica_id == p.id)
    if estado:
        query = query.filter(RegistroHoras.estado_validacion == RegistroHorasEstadoEnum(estado))
    if cursor:
        try:
            raw_date, last_id = cursor.split("|", 1)
            date = datetime.fromisoformat(raw_date)
            if not last_id or len(last_id) > 200:
                raise ValueError()
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise HTTPException(422, "El punto de continuación no es válido. Actualiza la bitácora.")
        query = query.filter(or_(RegistroHoras.fecha < date,
            and_(RegistroHoras.fecha == date, RegistroHoras.id < last_id)))
    rows = query.order_by(RegistroHoras.fecha.desc(), RegistroHoras.id.desc()).limit(limite + 1).all()
    more = len(rows) > limite
    rows = rows[:limite]
    next_cursor = f"{rows[-1].fecha.isoformat()}|{rows[-1].id}" if more else None
    count = totals[estado]["registros"] if estado else sum(t["registros"] for t in totals.values())
    return {"practica": practice_out(p, totals), "resumen": totals, "coincidencias": count,
        "registros": [to_record(r) for r in rows], "siguiente": next_cursor}


@router.get("/practicas/{practica_id}/actividad/{registro_id}")
def actividad(practica_id: str, registro_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    student(current_user)
    p = require_practice(db, current_user, practica_id)
    r = db.query(RegistroHoras).filter(RegistroHoras.practica_id == p.id, RegistroHoras.id == registro_id).first()
    if r is None:
        raise HTTPException(404, "La actividad no está disponible en esta práctica.")
    return {"practica": practice_out(p, summary(db, p.id)), "registro": to_record(r)}
