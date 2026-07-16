"""
Gestión de usuarios por el administrador (HU-12).
Rutas: /api/v1/admin/*
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import (
    Auditoria,
    Aula,
    AulaEstadoEnum,
    Empresa,
    Entrega,
    Inscripcion,
    Practica,
    PracticaEstadoEnum,
    RegistroAsistencia,
    RoleEnum,
    Tarea,
    User,
)
from app.schemas.schemas import (
    AsignarProfesorRequest,
    AuditoriaOut,
    AulaOut,
    MatriculaAlumnoOut,
    MatriculasOut,
    MatricularRequest,
    ReporteAulaOut,
    ReporteInstitucionalOut,
    ResumenAdminOut,
    UpdateAulaEstadoRequest,
    UpdateRolRequest,
    UsuarioAdminOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _solo_admin(user: User) -> None:
    if user.role.value != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo el administrador puede acceder.")


def _auditar(db: Session, user: User, accion: str, detalle: str) -> None:
    """Registra una acción administrativa en la bitácora de auditoría (HU-33)."""
    db.add(
        Auditoria(
            user_id=user.id,
            user_nombre=f"{user.nombres} {user.apellidos}",
            accion=accion,
            detalle=detalle,
            fecha=datetime.now(timezone.utc),
        )
    )


def _to_out(u: User) -> UsuarioAdminOut:
    return UsuarioAdminOut(
        id=u.id,
        nombres=u.nombres,
        apellidos=u.apellidos,
        email=u.email,
        role=u.role.value,
        createdAt=u.created_at.isoformat() if u.created_at else "",
    )


# ── GET /api/v1/admin/usuarios ────────────────────────────────────────────────


@router.get("/usuarios", response_model=list[UsuarioAdminOut])
def list_usuarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los usuarios del sistema ordenados por rol y apellido."""
    _solo_admin(current_user)
    usuarios = db.query(User).order_by(User.role, User.apellidos).all()
    return [_to_out(u) for u in usuarios]


# ── PUT /api/v1/admin/usuarios/{user_id}/rol ──────────────────────────────────


@router.put("/usuarios/{user_id}/rol", response_model=UsuarioAdminOut)
def update_rol(
    user_id: str,
    payload: UpdateRolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cambia el rol de un usuario. El admin no puede cambiar su propio rol."""
    _solo_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol.",
        )

    usuario = db.query(User).filter(User.id == user_id).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    rol_anterior = usuario.role.value
    usuario.role = RoleEnum(payload.role)
    _auditar(
        db,
        current_user,
        "CAMBIO_ROL",
        f"{usuario.nombres} {usuario.apellidos}: {rol_anterior} → {payload.role}",
    )
    db.commit()
    db.refresh(usuario)
    return _to_out(usuario)


# ── GET /api/v1/admin/resumen ─────────────────────────────────────────────────


@router.get("/resumen", response_model=ResumenAdminOut)
def resumen_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Panel de control administrativo (HU-23)."""
    _solo_admin(current_user)

    alumnos_matriculados = db.query(User).filter(User.role == RoleEnum.ALUMNO).count()

    profesores = db.query(User).filter(User.role == RoleEnum.PROFESOR).all()
    profesores_activos = 0
    for p in profesores:
        tiene_aula_activa = (
            db.query(Aula)
            .filter(Aula.profesor_id == p.id, Aula.estado == AulaEstadoEnum.ACTIVA)
            .first()
        )
        if tiene_aula_activa:
            profesores_activos += 1

    aulas_activas = db.query(Aula).filter(Aula.estado == AulaEstadoEnum.ACTIVA).count()

    # Empresa es hoy 1:1 por alumno (no un catálogo normalizado de centros de
    # prácticas); se cuenta por RUC distinto para no duplicar el mismo centro.
    rucs = {e.ruc for e in db.query(Empresa).all()}

    return ResumenAdminOut(
        alumnosMatriculados=alumnos_matriculados,
        profesoresActivos=profesores_activos,
        aulasActivas=aulas_activas,
        centrosDePracticas=len(rucs),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _aula_out(aula: Aula) -> AulaOut:
    return AulaOut(
        id=aula.id,
        nombre=aula.nombre,
        codigo=aula.codigo,
        descripcion=aula.descripcion,
        periodo=aula.periodo,
        profesorId=aula.profesor_id,
        profesorNombre=f"{aula.profesor.nombres} {aula.profesor.apellidos}"
        if aula.profesor
        else "—",
        estado=aula.estado.value,
        inscritos=aula.inscritos,
        createdAt=aula.created_at.isoformat() if aula.created_at else "",
    )


def _get_aula(aula_id: str, db: Session) -> Aula:
    aula = db.query(Aula).filter(Aula.id == aula_id).first()
    if aula is None:
        raise HTTPException(status_code=404, detail="Aula no encontrada.")
    return aula


# ── HU-29 · Cambiar estado de un aula (archivar / reactivar) ──────────────────


@router.put("/aulas/{aula_id}/estado", response_model=AulaOut)
def cambiar_estado_aula(
    aula_id: str,
    payload: UpdateAulaEstadoRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marca un aula como ACTIVA o CONCLUIDA (archivada)."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)
    aula.estado = AulaEstadoEnum(payload.estado)
    _auditar(db, current_user, "ESTADO_AULA", f"{aula.nombre} → {payload.estado}")
    db.commit()
    db.refresh(aula)
    return _aula_out(aula)


# ── HU-30 · Asignar profesor a un aula ────────────────────────────────────────


@router.put("/aulas/{aula_id}/profesor", response_model=AulaOut)
def asignar_profesor(
    aula_id: str,
    payload: AsignarProfesorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Asigna un profesor (jefe de prácticas) como responsable del aula."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)

    profesor = db.query(User).filter(User.id == payload.profesorId).first()
    if profesor is None:
        raise HTTPException(status_code=404, detail="Profesor no encontrado.")
    if profesor.role != RoleEnum.PROFESOR:
        raise HTTPException(status_code=422, detail="El usuario elegido no es profesor.")

    aula.profesor_id = profesor.id
    _auditar(
        db,
        current_user,
        "ASIGNAR_PROFESOR",
        f"{aula.nombre} → {profesor.nombres} {profesor.apellidos}",
    )
    db.commit()
    db.refresh(aula)
    return _aula_out(aula)


# ── HU-31 · Matrículas de un aula ─────────────────────────────────────────────


@router.get("/aulas/{aula_id}/matriculas", response_model=MatriculasOut)
def get_matriculas(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista todos los alumnos, marcando cuáles están inscritos en el aula."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)

    inscritos = {
        i.alumno_id
        for i in db.query(Inscripcion).filter(Inscripcion.aula_id == aula_id).all()
    }
    alumnos = (
        db.query(User)
        .filter(User.role == RoleEnum.ALUMNO)
        .order_by(User.apellidos, User.nombres)
        .all()
    )
    return MatriculasOut(
        aulaId=aula.id,
        aulaNombre=aula.nombre,
        alumnos=[
            MatriculaAlumnoOut(
                alumnoId=a.id,
                alumnoNombre=f"{a.nombres} {a.apellidos}",
                email=a.email,
                inscrito=a.id in inscritos,
            )
            for a in alumnos
        ],
    )


@router.post("/aulas/{aula_id}/matriculas", response_model=MatriculasOut)
def matricular(
    aula_id: str,
    payload: MatricularRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Inscribe un alumno en el aula. Idempotente (409 si ya está inscrito)."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)

    alumno = db.query(User).filter(User.id == payload.alumnoId).first()
    if alumno is None or alumno.role != RoleEnum.ALUMNO:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")

    ya = (
        db.query(Inscripcion)
        .filter(Inscripcion.aula_id == aula_id, Inscripcion.alumno_id == payload.alumnoId)
        .first()
    )
    if ya:
        raise HTTPException(status_code=409, detail="El alumno ya está matriculado.")

    db.add(Inscripcion(alumno_id=payload.alumnoId, aula_id=aula_id, semanas_totales=16))
    aula.inscritos = (aula.inscritos or 0) + 1
    _auditar(db, current_user, "MATRICULA", f"{alumno.nombres} {alumno.apellidos} → {aula.nombre}")
    db.commit()
    return get_matriculas(aula_id, db, current_user)


@router.delete("/aulas/{aula_id}/matriculas/{alumno_id}", response_model=MatriculasOut)
def desmatricular(
    aula_id: str,
    alumno_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retira la matrícula de un alumno del aula."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)

    ins = (
        db.query(Inscripcion)
        .filter(Inscripcion.aula_id == aula_id, Inscripcion.alumno_id == alumno_id)
        .first()
    )
    if ins is None:
        raise HTTPException(status_code=404, detail="El alumno no está matriculado.")

    db.delete(ins)
    aula.inscritos = max(0, (aula.inscritos or 0) - 1)
    _auditar(db, current_user, "RETIRO_MATRICULA", f"{alumno_id} ← {aula.nombre}")
    db.commit()
    return get_matriculas(aula_id, db, current_user)


# ── HU-32 · Reportes institucionales ──────────────────────────────────────────


@router.get("/reportes", response_model=ReporteInstitucionalOut)
def reportes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Agregados del programa: totales, prácticas por estado y detalle por aula."""
    _solo_admin(current_user)

    total_alumnos = db.query(User).filter(User.role == RoleEnum.ALUMNO).count()
    total_profesores = db.query(User).filter(User.role == RoleEnum.PROFESOR).count()
    aulas = db.query(Aula).order_by(Aula.created_at.desc()).all()
    aulas_activas = sum(1 for a in aulas if a.estado == AulaEstadoEnum.ACTIVA)

    practicas = db.query(Practica).all()
    en_curso = sum(1 for p in practicas if p.estado != PracticaEstadoEnum.CERRADA)
    cerradas = sum(1 for p in practicas if p.estado == PracticaEstadoEnum.CERRADA)
    horas_promedio = (
        round(sum(p.horas_acumuladas for p in practicas) / len(practicas), 1)
        if practicas
        else None
    )

    filas: list[ReporteAulaOut] = []
    for a in aulas:
        tareas = db.query(Tarea).filter(Tarea.aula_id == a.id).all()
        tarea_ids = [t.id for t in tareas]
        notas = []
        if tarea_ids:
            notas = [
                e.nota
                for e in db.query(Entrega).filter(Entrega.tarea_id.in_(tarea_ids)).all()
                if e.nota is not None
            ]
        promedio_notas = round(sum(notas) / len(notas), 2) if notas else None

        asist = db.query(RegistroAsistencia).filter(RegistroAsistencia.aula_id == a.id).all()
        asistencia_pct = (
            round(sum(1 for r in asist if r.presente) / len(asist) * 100) if asist else None
        )

        filas.append(
            ReporteAulaOut(
                aulaId=a.id,
                aulaNombre=a.nombre,
                periodo=a.periodo,
                profesorNombre=f"{a.profesor.nombres} {a.profesor.apellidos}"
                if a.profesor
                else "—",
                estado=a.estado.value,
                inscritos=a.inscritos,
                promedioNotas=promedio_notas,
                asistenciaPct=asistencia_pct,
            )
        )

    return ReporteInstitucionalOut(
        totalAlumnos=total_alumnos,
        totalProfesores=total_profesores,
        totalAulas=len(aulas),
        aulasActivas=aulas_activas,
        practicasEnCurso=en_curso,
        practicasCerradas=cerradas,
        horasPromedio=horas_promedio,
        aulas=filas,
    )


# ── HU-33 · Auditoría ─────────────────────────────────────────────────────────


@router.get("/auditoria", response_model=list[AuditoriaOut])
def list_auditoria(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bitácora de acciones administrativas, de la más reciente a la más antigua."""
    _solo_admin(current_user)
    registros = db.query(Auditoria).order_by(Auditoria.fecha.desc()).limit(200).all()
    return [
        AuditoriaOut(
            id=r.id,
            userNombre=r.user_nombre,
            accion=r.accion,
            detalle=r.detalle,
            fecha=r.fecha.isoformat() if r.fecha else "",
        )
        for r in registros
    ]
