"""Avisos dentro de la app, en la misma transacción del evento académico."""
from hashlib import sha256
from app.models.models import Inscripcion, Notificacion, NotificacionTipoEnum


def add_notice(db, user_id, event, tipo, title, message, target):
    notice_id = "n-" + sha256(f"{event}|{user_id}".encode()).hexdigest()
    db.add(Notificacion(id=notice_id, user_id=user_id, tipo=NotificacionTipoEnum(tipo),
        titulo=title[:200], mensaje=message, destino=target, leida=0))


def task_notices(db, task, revision=None):
    edited = revision is not None
    for (student_id,) in db.query(Inscripcion.alumno_id).filter(Inscripcion.aula_id == task.aula_id):
        add_notice(db, student_id, f"task:{task.id}:{revision if edited else 'created'}",
            "TAREA_ACTUALIZADA" if edited else "TAREA_ASIGNADA",
            "Tarea actualizada" if edited else "Nueva tarea en tu aula",
            f"{task.titulo}. Revisa las instrucciones y el plazo en el detalle.",
            {"tipo": "TAREA", "aulaId": task.aula_id, "tareaId": task.id})


def hours_notice(db, practice, record):
    approved = record.estado_validacion.value == "VALIDADO"
    add_notice(db, practice.practicante_id, f"hours:{record.id}:{record.revision}", "REVISION_HORAS",
        "Actividad validada" if approved else "Actividad por corregir",
        f"Tu supervisor {'validó' if approved else 'solicitó corregir'} una actividad de {record.horas} h. Consulta su revisión.",
        {"tipo": "ACTIVIDAD", "practicaId": practice.id, "registroId": record.id})
