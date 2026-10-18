"""Expediente visible por vínculo, evaluación autenticada y cierre docente."""
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.core.deps import get_current_user
from app.core.practice_access import require_practice
from app.core.expediente import audit, build, close, editable, encoded, evaluation, evaluation_data, expediente_row, name, now
from app.db.session import get_db
from app.models.models import Evaluacion, EvaluacionEstadoEnum, ExpedientePractica, Meta, Supervisor, Tarea, User
from app.schemas.expediente import CerrarExpedienteRequest, EvaluacionRequest, RequisitosRequest

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


@router.get("/capacidades")
def capacidades(current_user: User = Depends(get_current_user)):
    return {"versionExpediente": 1, "evaluacionSupervisor": True, "cierreConRequisitos": True, "pdf": True}


@router.get("/{practica_id}")
def get_expediente(practica_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return build(db, require_practice(db, current_user, practica_id))


@router.put("/{practica_id}/requisitos")
def guardar_requisitos(practica_id: str, payload: RequisitosRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    practica = editable(db, current_user, practica_id, {"PROFESOR", "ADMIN"})
    row = expediente_row(db, practica_id)
    values = payload.model_dump(exclude={"revision"})
    previous = json.loads(row.requisitos) if row and row.requisitos else None
    if previous and row.revision == payload.revision + 1 and all(previous.get(k) == v for k, v in values.items()):
        return build(db, practica)
    if (row.revision if row else 0) != payload.revision:
        raise HTTPException(409, "Los requisitos cambiaron. Consulta la versión actual.")
    task_ids = {t.id for t in db.query(Tarea).filter(Tarea.aula_id == practica.aula_id).all()}
    target_ids = {m.id for m in db.query(Meta).filter(Meta.practica_id == practica_id).all()}
    if not set(payload.tareas).issubset(task_ids) or not set(payload.metas).issubset(target_ids):
        raise HTTPException(422, "Selecciona tareas del aula y metas de esta práctica.")
    if row is None:
        row = ExpedientePractica(practica_id=practica_id, revision=0)
        db.add(row)
    row.revision += 1
    row.requisitos = encoded({**values, "responsable": name(current_user), "responsableId": current_user.id, "fecha": now()})
    audit(db, current_user, "REQUISITOS_CIERRE", f"Práctica {practica_id}; revisión {row.revision}; tareas: {len(payload.tareas)}; metas: {len(payload.metas)}. {payload.motivo}")
    db.commit()
    return build(db, practica)


@router.put("/{practica_id}/evaluacion")
def guardar_evaluacion(practica_id: str, payload: EvaluacionRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    practica = editable(db, current_user, practica_id, {"SUPERVISOR"})
    supervisor = db.query(Supervisor).filter(Supervisor.empresa_id == practica.empresa_id, Supervisor.user_id == current_user.id).first()
    if supervisor is None:
        raise HTTPException(403, "La práctica debe tener un centro vinculado a tu cuenta de supervisor.")
    row = evaluation(db, practica)
    previous = evaluation_data(row)
    values = payload.model_dump(exclude={"revision"})
    if previous and previous["revision"] == payload.revision + 1 and previous["supervisorId"] == current_user.id and all(previous.get(k) == v for k, v in values.items()):
        return build(db, practica)
    if (previous["revision"] if previous else 0) != payload.revision:
        raise HTTPException(409, "La evaluación cambió. Consulta los datos actuales.")
    if row is None:
        row = Evaluacion(id="ev-final-" + practica_id, practica_id=practica_id, empresa_id=practica.empresa_id, periodo=practica.periodo)
        db.add(row)
    row.empresa_id = practica.empresa_id
    row.estado = EvaluacionEstadoEnum.COMPLETADA
    row.contenido = encoded({**values, "revision": payload.revision + 1, "supervisorId": current_user.id,
        "supervisorNombre": name(current_user), "empresaId": practica.empresa_id, "fecha": now()})
    audit(db, current_user, "EVALUACION_SUPERVISOR", f"Práctica {practica_id}; revisión {payload.revision + 1}; conclusión: {payload.conclusion}.")
    db.commit()
    return build(db, practica)


@router.post("/{practica_id}/cerrar")
def cerrar_expediente(practica_id: str, payload: CerrarExpedienteRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return close(db, current_user, practica_id, payload)


@router.get("/{practica_id}/pdf", response_class=Response)
def descargar_pdf(practica_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.core.expediente_pdf import render_pdf
    practica = require_practice(db, current_user, practica_id)
    data = build(db, practica)
    suffix = "final-v1" if data["cerrado"] and data["cierre"] else "en-curso"
    # El nombre nunca incorpora datos personales ni identificadores recibidos del cliente.
    import hashlib
    filename = "expediente-" + hashlib.sha256(practica_id.encode()).hexdigest()[:12] + "-" + suffix + ".pdf"
    return Response(render_pdf(data), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
