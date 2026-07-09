"""
Vistas del profesor/asesor (HU-11): progreso de practicantes.
Rutas: /api/v1/profesor/*
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Aula, Entrega, Inscripcion, Tarea, User
from app.schemas.schemas import PracticanteProgresoOut

router = APIRouter(prefix="/profesor", tags=["profesor"])


def _solo_profesor_o_admin(user: User) -> None:
    if user.role.value not in ("PROFESOR", "ADMIN"):
        raise HTTPException(status_code=403, detail="Acceso restringido.")


# ── GET /api/v1/profesor/practicantes ─────────────────────────────────────────


@router.get("/practicantes", response_model=list[PracticanteProgresoOut])
def list_practicantes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista todos los practicantes inscritos en las aulas del profesor,
    con su avance, semanas y estado de entrega de tareas.
    El rol ADMIN ve todas las aulas.
    """
    _solo_profesor_o_admin(current_user)

    if current_user.role.value == "ADMIN":
        aulas = db.query(Aula).all()
    else:
        aulas = db.query(Aula).filter(Aula.profesor_id == current_user.id).all()

    aula_map = {a.id: a for a in aulas}
    aula_ids = list(aula_map.keys())

    inscripciones = (
        db.query(Inscripcion)
        .filter(Inscripcion.aula_id.in_(aula_ids))
        .all()
    )

    resultado: list[PracticanteProgresoOut] = []
    for ins in inscripciones:
        aula = aula_map[ins.aula_id]
        alumno: User = ins.alumno

        tareas = db.query(Tarea).filter(Tarea.aula_id == ins.aula_id).all()
        tareas_total = len(tareas)
        tareas_entregadas = 0
        if tareas_total > 0:
            tareas_entregadas = (
                db.query(Entrega)
                .filter(
                    Entrega.alumno_id == ins.alumno_id,
                    Entrega.tarea_id.in_([t.id for t in tareas]),
                )
                .count()
            )

        resultado.append(
            PracticanteProgresoOut(
                alumnoId=alumno.id,
                alumnoNombre=f"{alumno.nombres} {alumno.apellidos}",
                alumnoEmail=alumno.email,
                aulaId=aula.id,
                aulaNombre=aula.nombre,
                progreso=ins.progreso,
                semanaActual=ins.semana_actual,
                semanasTotales=ins.semanas_totales,
                estado=aula.estado.value,
                tareasEntregadas=tareas_entregadas,
                tareasTotal=tareas_total,
            )
        )

    resultado.sort(key=lambda x: (x.aulaNombre, x.alumnoNombre))
    return resultado
