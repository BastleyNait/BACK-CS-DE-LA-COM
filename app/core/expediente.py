"""Un único circuito de requisitos, evaluación, cierre y copia documental."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import load_only
from app.core.practice_access import require_practice, sync_hours
from app.models.models import (
    Auditoria, Empresa, Entrega, Evaluacion, EvaluacionEstadoEnum,
    ExpedientePractica, Inscripcion, Meta, MetaTipoEnum, PracticaEstadoEnum,
    RegistroHoras, RegistroHorasEstadoEnum, Supervisor, Tarea,
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def name(user):
    return f"{user.nombres} {user.apellidos}"


def now():
    return datetime.now(timezone.utc).isoformat()


def audit(db, user, action, detail):
    db.add(Auditoria(user_id=user.id, user_nombre=name(user), accion=action, detalle=detail))


def evaluation(db, practica):
    rows = db.query(Evaluacion).filter(Evaluacion.practica_id == practica.id).order_by(Evaluacion.id).all()
    # Una evaluación ya completada en este circuito prevalece sobre propuestas antiguas.
    return next((e for e in rows if e.contenido), rows[0] if rows else None)


def evaluation_data(row):
    return json.loads(row.contenido) if row and row.contenido else None


def expediente_row(db, practica_id):
    return db.get(ExpedientePractica, practica_id)


def editable(db, user, practica_id, roles):
    if user.role.value not in roles:
        raise HTTPException(403, "Tu rol no permite realizar esta operación.")
    practica = require_practice(db, user, practica_id, lock=True)
    if practica.estado == PracticaEstadoEnum.CERRADA:
        raise HTTPException(409, "La práctica está cerrada. Su expediente conserva los datos del cierre.")
    return practica


def student_summary(result):
    """Proyección de consulta: nunca expone una revisión utilizable para cerrar."""
    keys = ("practica", "centro", "supervisor", "evaluacion", "evaluacionVigente",
            "checklist", "puedeCerrar", "cerrado", "cierre")
    summary = {key: result[key] for key in keys}
    config = result["configuracion"]
    summary["configuracion"] = {key: config[key] for key in (
        "notaMinima", "motivo", "responsable", "fecha")} if config else None
    return summary


def build(db, practica, frozen=True, compact=False):
    record = expediente_row(db, practica.id)
    if frozen and record and record.cierre:
        saved = json.loads(record.cierre)
        return student_summary(saved) if compact else saved
    company = db.get(Empresa, practica.empresa_id) if practica.empresa_id else None
    supervisor = db.query(Supervisor).filter(Supervisor.empresa_id == practica.empresa_id).first() if company else None
    config = json.loads(record.requisitos) if record and record.requisitos else None
    assessment = evaluation_data(evaluation(db, practica))
    required_tasks, required_targets = set(config["tareas"] if config else []), set(config["metas"] if config else [])
    if compact:
        hours = []
        approved = int(db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(
            RegistroHoras.practica_id == practica.id,
            RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).scalar())
    else:
        hours = db.query(RegistroHoras).filter(RegistroHoras.practica_id == practica.id).order_by(RegistroHoras.fecha, RegistroHoras.id).all()
        approved = sum(h.horas for h in hours if h.estado_validacion == RegistroHorasEstadoEnum.VALIDADO)
    tasks_query = db.query(Tarea).filter(Tarea.aula_id == practica.aula_id)
    deliveries_query = db.query(Entrega).join(Tarea, Entrega.tarea_id == Tarea.id).filter(
        Tarea.aula_id == practica.aula_id, Entrega.alumno_id == practica.practicante_id)
    targets_query = db.query(Meta).filter(Meta.practica_id == practica.id)
    if compact:
        tasks_query = tasks_query.filter(Tarea.id.in_(required_tasks)).options(load_only(Tarea.id, Tarea.titulo))
        deliveries_query = deliveries_query.filter(Tarea.id.in_(required_tasks)).options(load_only(Entrega.id, Entrega.tarea_id, Entrega.nota))
        targets_query = targets_query.filter(Meta.id.in_(required_targets)).options(load_only(
            Meta.id, Meta.tipo, Meta.cantidad_objetivo, Meta.cantidad_alcanzada))
    tasks = tasks_query.order_by(Tarea.created_at, Tarea.id).all()
    deliveries = {e.tarea_id: e for e in deliveries_query.order_by(Entrega.id).all()}
    targets = targets_query.order_by(Meta.created_at, Meta.id).all()
    minimum = config["notaMinima"] if config else None
    task_rows = []
    for task in tasks:
        delivery = deliveries.get(task.id)
        passed = bool(delivery and delivery.nota is not None and (minimum is None or delivery.nota >= minimum))
        task_rows.append({"id": task.id, "titulo": task.titulo, "obligatoria": task.id in required_tasks,
            "entregaId": delivery.id if delivery else None, "nota": delivery.nota if delivery else None,
            "retroalimentacion": delivery.retroalimentacion if delivery and not compact else None, "cumplida": passed})
    target_rows = [{"id": m.id, "tipo": m.tipo.value, "descripcion": (m.descripcion or "") if not compact else "",
        "obligatoria": m.id in required_targets, "objetivo": m.cantidad_objetivo,
        "alcanzada": approved if m.tipo == MetaTipoEnum.HORAS else m.cantidad_alcanzada,
        "cumplida": (approved if m.tipo == MetaTipoEnum.HORAS else m.cantidad_alcanzada) >= m.cantidad_objetivo} for m in targets]
    enrolled = db.query(Inscripcion.id).filter(Inscripcion.aula_id == practica.aula_id, Inscripcion.alumno_id == practica.practicante_id).first() is not None
    selected_tasks = [t for t in task_rows if t["obligatoria"]]
    selected_targets = [m for m in target_rows if m["obligatoria"]]
    current_assessment = bool(assessment and supervisor and assessment["supervisorId"] == supervisor.user_id and assessment["empresaId"] == practica.empresa_id)
    checklist = [
        {"id": "matricula", "titulo": "Matrícula vigente en el aula", "cumplido": enrolled, "detalle": "Matriculado" if enrolled else "Solicita revisar la matrícula."},
        {"id": "centro", "titulo": "Centro y supervisor con acceso", "cumplido": bool(company and supervisor and supervisor.user_id), "detalle": company.razon_social if company else "Falta asociar un centro a la práctica."},
        {"id": "requisitos", "titulo": "Requisitos confirmados por el docente", "cumplido": config is not None, "detalle": config["motivo"] if config else "El docente debe confirmar qué tareas y metas exige este expediente."},
        {"id": "horas", "titulo": "Horas validadas", "cumplido": approved >= practica.horas_minimas, "detalle": f"{approved} / {practica.horas_minimas} h; mínimo configurado para esta práctica."},
        {"id": "evaluacion", "titulo": "Evaluación favorable del supervisor", "cumplido": bool(current_assessment and assessment["conclusion"] == "FAVORABLE"), "detalle": "Evaluación favorable registrada" if current_assessment and assessment["conclusion"] == "FAVORABLE" else "Pendiente o requiere mejoras."},
        {"id": "tareas", "titulo": "Tareas exigidas y revisadas", "cumplido": required_tasks.issubset({t["id"] for t in task_rows}) and all(t["cumplida"] for t in selected_tasks), "detalle": f"{sum(t['cumplida'] for t in selected_tasks)} / {len(required_tasks)} tareas exigidas"},
        {"id": "metas", "titulo": "Metas exigidas completadas", "cumplido": required_targets.issubset({m["id"] for m in target_rows}) and all(m["cumplida"] for m in selected_targets), "detalle": f"{sum(m['cumplida'] for m in selected_targets)} / {len(required_targets)} metas exigidas"},
    ]
    result = {"practica": {"id": practica.id, "practicanteId": practica.practicante_id, "practicanteNombre": name(practica.practicante),
        "aulaId": practica.aula_id, "aulaNombre": practica.aula.nombre, "docenteNombre": name(practica.aula.profesor),
        "periodo": practica.periodo, "horasMinimas": practica.horas_minimas, "horasValidadas": approved,
        "estado": "CERRADA" if practica.estado == PracticaEstadoEnum.CERRADA else "LISTA_PARA_CIERRE" if approved >= practica.horas_minimas else "EN_CURSO", "fechaInicio": practica.fecha_inicio.isoformat() if practica.fecha_inicio else None},
        "centro": {"id": company.id, "nombre": company.razon_social, "ruc": company.ruc, "direccion": company.direccion} if company else None,
        "supervisor": {"id": supervisor.id, "userId": supervisor.user_id, "nombre": f"{supervisor.nombres} {supervisor.apellidos}", "cargo": supervisor.cargo} if supervisor else None,
        "configuracion": config, "revisionConfiguracion": record.revision if record else 0,
        "evaluacion": assessment, "evaluacionVigente": current_assessment,
        "tareas": task_rows, "metas": target_rows,
        "horas": [{"id": h.id, "fecha": h.fecha.isoformat(), "horas": h.horas, "descripcion": h.descripcion,
                   "estado": h.estado_validacion.value, "observacion": h.observacion} for h in hours],
        "checklist": checklist, "puedeCerrar": all(c["cumplido"] for c in checklist),
        "cerrado": practica.estado == PracticaEstadoEnum.CERRADA, "cierre": None}
    if compact:
        return student_summary(result)
    result["revision"] = hashlib.sha256(encoded(result).encode()).hexdigest()
    return result


def close(db, user, practica_id, payload):
    if user.role.value not in {"PROFESOR", "ADMIN"}:
        raise HTTPException(403, "Solo el docente responsable o administración puede cerrar la práctica.")
    practica = require_practice(db, user, practica_id, lock=True)
    row = expediente_row(db, practica_id)
    if row and row.cierre:
        saved = json.loads(row.cierre)
        if saved["cierre"]["revisionConfirmada"] != payload.revision or saved["cierre"]["motivo"] != payload.motivo:
            raise HTTPException(409, "La práctica ya está cerrada. Consulta el expediente conservado.")
        return saved
    if practica.estado == PracticaEstadoEnum.CERRADA:
        raise HTTPException(409, "Cierre anterior sin copia documental. Requiere revisión administrativa.")
    sync_hours(db, practica)
    result = build(db, practica)
    if payload.revision != result["revision"]:
        raise HTTPException(409, "El expediente cambió. Actualiza y revisa sus requisitos antes de cerrar.")
    if not result["puedeCerrar"]:
        raise HTTPException(422, "Faltan requisitos: " + "; ".join(c["titulo"] for c in result["checklist"] if not c["cumplido"]))
    # Las modificaciones de horas, evaluación, metas y notas toman este mismo bloqueo.
    practica.estado = PracticaEstadoEnum.CERRADA
    practica.fecha_cierre = datetime.now(timezone.utc)
    practica.validado_por = name(user)
    result["cerrado"] = True
    result["practica"]["estado"] = "CERRADA"
    result["cierre"] = {"version": 1, "fecha": practica.fecha_cierre.isoformat(), "responsable": name(user),
        "responsableId": user.id, "motivo": payload.motivo, "revisionConfirmada": payload.revision}
    row.cierre = encoded(result)
    audit(db, user, "PRACTICA_CERRADA", f"Práctica {practica.id}; expediente v1; revisión {payload.revision}. Motivo: {payload.motivo}")
    db.commit()
    return result
