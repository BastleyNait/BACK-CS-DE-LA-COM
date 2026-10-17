"""Fechas y trazabilidad transaccional de la bitácora."""
from datetime import datetime, date, time, timezone, timedelta
from fastapi import HTTPException
from app.models.models import Auditoria, HistorialHoras
from app.schemas.schemas import RegistroHorasOut


def activity_date(value):
    lima = timezone(timedelta(hours=-5))
    day = datetime.now(lima).date()
    if value:
        try:
            if len(value) == 10:
                day = date.fromisoformat(value)
            else:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
                day = parsed.astimezone(lima).date()
        except ValueError:
            raise HTTPException(422, "Fecha inválida. Usa AAAA-MM-DD.")
    if day > datetime.now(lima).date():
        raise HTTPException(422, "No puedes registrar actividades futuras.")
    return datetime.combine(day, time(12), tzinfo=lima).astimezone(timezone.utc)


def to_record(r):
    return RegistroHorasOut(id=r.id, practicaId=r.practica_id, fecha=r.fecha.isoformat(),
        horas=r.horas, descripcion=r.descripcion, estadoValidacion=r.estado_validacion.value,
        revision=r.revision, observacion=r.observacion)


def track_change(db, user, registro, accion, antes=None):
    """Se confirma junto con el registro; una revisión produce un solo evento."""
    nombre = f"{user.nombres} {user.apellidos}"
    despues = to_record(registro)
    db.add(HistorialHoras(registro_id=registro.id, revision=registro.revision,
        user_id=user.id, user_nombre=nombre, accion=accion,
        antes=antes.model_dump_json() if antes else None, despues=despues.model_dump_json()))
    db.add(Auditoria(user_id=user.id, user_nombre=nombre, accion=f"HORAS_{accion}",
        detalle=f"{accion.capitalize()} de actividad {registro.id}: {registro.horas} h; "
                f"{registro.estado_validacion.value}. " + registro.observacion))
