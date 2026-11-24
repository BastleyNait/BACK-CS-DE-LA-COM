"""
Gestión de usuarios por el administrador (HU-12).
Rutas: /api/v1/admin/*
"""

import base64
import hashlib
import json
from sqlalchemy import and_, case, func, or_, text
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.routers.staff_pages import _alphabetic, _name, _search
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
    Supervisor,
    RegistroHoras,
    RegistroHorasEstadoEnum,
)
from app.schemas.schemas import (
    AsignarProfesorRequest,
    CreateAulaRequest,
    EstablecerMatriculaRequest,
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


@router.get("/capacidades")
def capacidades(current_user: User = Depends(get_current_user)):
    _solo_admin(current_user)
    return {"versionAdministracion": 1}


@router.get("/aulas", response_model=list[AulaOut])
def list_aulas_admin(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_admin(current_user)
    counts = dict(db.query(Inscripcion.aula_id, func.count(func.distinct(Inscripcion.alumno_id))).group_by(Inscripcion.aula_id).all())
    return [_aula_out(a).model_copy(update={"inscritos": counts.get(a.id, 0)}) for a in db.query(Aula).order_by(Aula.created_at.desc(), Aula.id).all()]


@router.post("/aulas", response_model=AulaOut, status_code=201)
def crear_aula_admin(payload: CreateAulaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_admin(current_user)
    from app.routers.aulas import create_aula
    return create_aula(payload, db, current_user)


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

    # Serializa cambios de administradores y vuelve a comprobar al actor tras esperar.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()::text), 1501)"))
    db.refresh(current_user)
    _solo_admin(current_user)
    usuario = db.query(User).filter(User.id == user_id).populate_existing().with_for_update().first()
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado.")
    if usuario.role.value == payload.role:
        return _to_out(usuario)
    if usuario.role.value != payload.anterior:
        raise HTTPException(409, "El rol cambió. Consulta el usuario actualizado.")
    linked = (db.query(Aula.id).filter(Aula.profesor_id == user_id).first()
        or db.query(Inscripcion.id).filter(Inscripcion.alumno_id == user_id).first()
        or db.query(Practica.id).filter(Practica.practicante_id == user_id).first()
        or db.query(Empresa.id).filter(Empresa.practicante_id == user_id).first()
        or db.query(Supervisor.id).filter(Supervisor.user_id == user_id).first())
    if linked:
        raise HTTPException(409, "El usuario tiene asignaciones académicas. Resuélvelas antes de cambiar su rol.")

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


def _get_aula(aula_id: str, db: Session, lock=False) -> Aula:
    query = db.query(Aula).filter(Aula.id == aula_id)
    if lock:
        query = query.populate_existing().with_for_update()
    aula = query.first()
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
    aula = _get_aula(aula_id, db, lock=True)
    if aula.estado.value == payload.estado:
        return _aula_out(aula)
    if aula.estado.value != payload.anterior:
        raise HTTPException(409, "El estado del aula cambió. Consulta los datos actuales.")
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
    aula = _get_aula(aula_id, db, lock=True)

    if aula.profesor_id == payload.profesorId:
        return _aula_out(aula)
    if aula.profesor_id != payload.anterior:
        raise HTTPException(409, "El docente responsable cambió. Consulta el aula actual.")
    profesor = db.query(User).filter(User.id == payload.profesorId).populate_existing().with_for_update().first()
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
        revision=_roster_revision(db, aula),
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


def _roster_revision(db, aula):
    ids = sorted({r.alumno_id for r in db.query(Inscripcion).filter(Inscripcion.aula_id == aula.id).all()})
    return hashlib.sha256(json.dumps([aula.id, aula.estado.value, ids], separators=(",", ":")).encode()).hexdigest()


def _set_matricula(aula_id, alumno_id, desired, db, user, revision=None):
    _solo_admin(user)
    aula = _get_aula(aula_id, db, lock=True)
    alumno = db.query(User).filter(User.id == alumno_id).populate_existing().with_for_update().first()
    if not alumno or alumno.role != RoleEnum.ALUMNO:
        raise HTTPException(404, "Alumno no disponible.")
    rows = db.query(Inscripcion).filter(Inscripcion.aula_id == aula_id, Inscripcion.alumno_id == alumno_id).all()
    if bool(rows) == desired:
        return get_matriculas(aula_id, db, user)
    if aula.estado != AulaEstadoEnum.ACTIVA:
        raise HTTPException(409, "Reactiva el aula antes de modificar sus matrículas.")
    if revision is not None and revision != _roster_revision(db, aula):
        raise HTTPException(409, "El padrón cambió. Consulta las matrículas actuales.")
    if desired:
        db.add(Inscripcion(alumno_id=alumno_id, aula_id=aula_id, semanas_totales=16))
    else:
        for row in rows: db.delete(row)
    db.flush()
    aula.inscritos = db.query(func.count(func.distinct(Inscripcion.alumno_id))).filter(Inscripcion.aula_id == aula_id).scalar()
    _auditar(db, user, "MATRICULA" if desired else "RETIRO_MATRICULA", f"{alumno.nombres} {alumno.apellidos} {'→' if desired else '←'} {aula.nombre}")
    db.commit()
    return get_matriculas(aula_id, db, user)


@router.put("/aulas/{aula_id}/matriculas/{alumno_id}", response_model=MatriculasOut)
def establecer_matricula(aula_id: str, alumno_id: str, payload: EstablecerMatriculaRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _set_matricula(aula_id, alumno_id, payload.inscrito, db, current_user, payload.revision)


@router.post("/aulas/{aula_id}/matriculas", response_model=MatriculasOut)
def matricular(aula_id: str, payload: MatricularRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _set_matricula(aula_id, payload.alumnoId, True, db, current_user)


@router.delete("/aulas/{aula_id}/matriculas/{alumno_id}", response_model=MatriculasOut)
def desmatricular(aula_id: str, alumno_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _set_matricula(aula_id, alumno_id, False, db, current_user)


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
    hours = dict(db.query(RegistroHoras.practica_id, func.sum(RegistroHoras.horas)).filter(RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).group_by(RegistroHoras.practica_id).all())
    horas_promedio = round(sum(hours.get(p.id, 0) for p in practicas) / len(practicas), 1) if practicas else None
    counts = dict(db.query(Inscripcion.aula_id, func.count(func.distinct(Inscripcion.alumno_id))).group_by(Inscripcion.aula_id).all())

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
                inscritos=counts.get(a.id, 0),
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


# ── Lecturas paginadas de administración ──────────────────────────────────────
# Páginas en SQL con totales globales y detalle puntual, como el personal.
# Solo lectura: crear, cambiar roles/estados/docentes y matricular conservan
# sus circuitos confirmados y siguen disponibles en las rutas anteriores.


def _limite(limite: int) -> None:
    if not 1 <= limite <= 40:
        raise HTTPException(422, "El tamaño de página debe estar entre 1 y 40.")


def _aulas_admin_base(db: Session):
    """Proyección de aulas con docente; la misma que el personal consulta."""
    return db.query(Aula.id, Aula.nombre, Aula.codigo, Aula.descripcion, Aula.periodo, Aula.profesor_id,
        Aula.estado, Aula.inscritos, _name().label("docente")).join(User, User.id == Aula.profesor_id)


def _fila_aula(row) -> dict:
    return {"id": row.id, "nombre": row.nombre, "codigo": row.codigo, "descripcion": row.descripcion,
        "periodo": row.periodo, "profesorId": row.profesor_id, "profesorNombre": row.docente,
        "estado": row.estado.value, "inscritos": row.inscritos}


def _filtro_aulas(query, estado: str, q: str):
    if estado != "TODAS":
        query = query.filter(Aula.estado == (AulaEstadoEnum.ACTIVA if estado == "ACTIVA" else AulaEstadoEnum.CONCLUIDA))
    if q:
        query = query.filter(func.lower(Aula.nombre + " " + Aula.codigo + " " + Aula.periodo + " " + _name()).contains(q, autoescape=True))
    return query


def _estado_aulas(estado: str) -> None:
    if estado not in ("TODAS", "ACTIVA", "CONCLUIDA"):
        raise HTTPException(422, "Selecciona todas, activas o concluidas.")


@router.get("/usuarios/pagina")
def usuarios_pagina(rol: str = "TODOS", q: str = "", limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Directorio de cuentas por páginas con búsqueda y rol; totales globales en SQL."""
    _solo_admin(current_user)
    _limite(limite)
    if rol not in ("TODOS", "ALUMNO", "PROFESOR", "SUPERVISOR", "ADMIN"):
        raise HTTPException(422, "Selecciona un rol válido.")
    q = _search(q)
    query = db.query(User)
    if rol != "TODOS":
        query = query.filter(User.role == RoleEnum(rol))
    if q:
        query = query.filter(func.lower(User.nombres + " " + User.apellidos + " " + User.email).contains(q, autoescape=True))
    page = _alphabetic(query, func.lower(User.apellidos + " " + User.nombres), User.id,
        f"usuarios:{current_user.id}:{rol}:{q}", limite, cursor, lambda row: _to_out(row[0]).model_dump(mode="json"))
    page["totalDocentes"] = db.query(User).filter(User.role == RoleEnum.PROFESOR).count()
    return page


@router.get("/aulas/pagina")
def aulas_pagina(estado: str = "TODAS", q: str = "", limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Aulas administrables por páginas con búsqueda y estado; aulas activas globales."""
    _solo_admin(current_user)
    _limite(limite)
    _estado_aulas(estado)
    q = _search(q)
    query = _filtro_aulas(_aulas_admin_base(db), estado, q)
    page = _alphabetic(query, func.lower(Aula.nombre), Aula.id,
        f"aulas-admin:{current_user.id}:{estado}:{q}", limite, cursor, _fila_aula)
    page["aulasActivas"] = db.query(Aula).filter(Aula.estado == AulaEstadoEnum.ACTIVA).count()
    return page


@router.get("/aulas/{aula_id}/matriculas/pagina")
def matriculas_pagina(aula_id: str, estado: str = "TODOS", q: str = "", limite: int = Query(20, ge=1, le=40),
                      cursor: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Padrón de matrícula por páginas; la revisión protege la escritura confirmada."""
    _solo_admin(current_user)
    _limite(limite)
    aula = _get_aula(aula_id, db)
    if estado not in ("TODOS", "MATRICULADOS", "SIN_MATRICULA"):
        raise HTTPException(422, "Selecciona todos, matriculados o sin matrícula.")
    q = _search(q)
    inscritos = {i.alumno_id for i in db.query(Inscripcion.alumno_id).filter(Inscripcion.aula_id == aula_id)}
    query = db.query(User).filter(User.role == RoleEnum.ALUMNO)
    if estado != "TODOS":
        en_aula = db.query(Inscripcion.id).filter(Inscripcion.aula_id == aula_id, Inscripcion.alumno_id == User.id).exists()
        query = query.filter(en_aula if estado == "MATRICULADOS" else ~en_aula)
    if q:
        query = query.filter(func.lower(User.nombres + " " + User.apellidos + " " + User.email).contains(q, autoescape=True))

    def pack(row):
        u = row[0]
        return {"alumnoId": u.id, "alumnoNombre": f"{u.nombres} {u.apellidos}", "email": u.email, "inscrito": u.id in inscritos}

    page = _alphabetic(query, func.lower(User.apellidos + " " + User.nombres), User.id,
        f"matriculas:{current_user.id}:{aula_id}:{estado}:{q}", limite, cursor, pack)
    return {"revision": _roster_revision(db, aula), "aulaId": aula.id, "aulaNombre": aula.nombre,
        "items": page["items"], "total": page["total"], "siguiente": page["siguiente"],
        "matriculados": len(inscritos)}


@router.get("/aulas/{aula_id}")
def detalle_aula_admin(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ficha exacta del aula para gestionar matrículas sin recargar el directorio."""
    _solo_admin(current_user)
    aula = _get_aula(aula_id, db)
    counts = dict(db.query(Inscripcion.aula_id, func.count(func.distinct(Inscripcion.alumno_id)))
        .filter(Inscripcion.aula_id == aula_id).group_by(Inscripcion.aula_id).all())
    return _aula_out(aula).model_copy(update={"inscritos": counts.get(aula.id, 0)}).model_dump(mode="json")


@router.get("/reportes/pagina")
def reportes_pagina(estado: str = "TODAS", q: str = "", limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resumen global del programa en SQL y aulas por páginas con indicadores por página."""
    _solo_admin(current_user)
    _limite(limite)
    _estado_aulas(estado)
    q = _search(q)
    total_practicas = db.query(Practica).count()
    estados = dict(db.query(Practica.estado, func.count(Practica.id)).group_by(Practica.estado).all())
    horas_por_practica = (
        db.query(Practica.id, func.coalesce(func.sum(RegistroHoras.horas), 0).label("horas"))
        .outerjoin(RegistroHoras, and_(RegistroHoras.practica_id == Practica.id,
            RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO))
        .group_by(Practica.id).subquery())
    promedio = db.query(func.avg(horas_por_practica.columns.horas)).scalar()
    resumen = {
        "totalAlumnos": db.query(User).filter(User.role == RoleEnum.ALUMNO).count(),
        "totalProfesores": db.query(User).filter(User.role == RoleEnum.PROFESOR).count(),
        "totalAulas": db.query(Aula).count(),
        "aulasActivas": db.query(Aula).filter(Aula.estado == AulaEstadoEnum.ACTIVA).count(),
        "practicasEnCurso": total_practicas - estados.get(PracticaEstadoEnum.CERRADA, 0),
        "practicasCerradas": estados.get(PracticaEstadoEnum.CERRADA, 0),
        "horasPromedio": round(promedio, 1) if promedio is not None else None,
    }
    query = _filtro_aulas(_aulas_admin_base(db), estado, q)
    page = _alphabetic(query, func.lower(Aula.nombre), Aula.id,
        f"reportes:{current_user.id}:{estado}:{q}", limite, cursor, _fila_aula)
    ids = [item["id"] for item in page["items"]]
    if ids:
        counts = dict(db.query(Inscripcion.aula_id, func.count(func.distinct(Inscripcion.alumno_id)))
            .filter(Inscripcion.aula_id.in_(ids)).group_by(Inscripcion.aula_id).all())
        promedios = dict(db.query(Tarea.aula_id, func.avg(Entrega.nota)).join(Entrega, Entrega.tarea_id == Tarea.id)
            .filter(Tarea.aula_id.in_(ids), Entrega.nota.is_not(None)).group_by(Tarea.aula_id).all())
        asistencias = {fila[0]: (fila[1], fila[2] or 0) for fila in db.query(RegistroAsistencia.aula_id,
            func.count(RegistroAsistencia.id), func.sum(case((RegistroAsistencia.presente == 1, 1), else_=0)))
            .filter(RegistroAsistencia.aula_id.in_(ids)).group_by(RegistroAsistencia.aula_id).all()}
        for item in page["items"]:
            item["aulaId"] = item["id"]
            item["aulaNombre"] = item["nombre"]
            item["inscritos"] = counts.get(item["id"], 0)
            nota = promedios.get(item["id"])
            item["promedioNotas"] = round(nota, 2) if nota is not None else None
            registrados, presentes = asistencias.get(item["id"], (0, 0))
            item["asistenciaPct"] = round(presentes / registrados * 100) if registrados else None
    return {"resumen": resumen, "items": page["items"], "total": page["total"], "siguiente": page["siguiente"]}


def _detalle_asistencia(row) -> dict | None:
    """Estructura del detalle JSON solo para entradas de asistencia académica."""
    if row.accion != "ASISTENCIA_ACADEMICA":
        return None
    try:
        value = json.loads(row.detalle)
        if not isinstance(value, dict) or not isinstance(value.get("aulaId"), str):
            return None
        filas = []
        for key in ("antes", "despues"):
            grupo = value.get(key)
            if not isinstance(grupo, list) or not all(isinstance(f, dict) and isinstance(f.get("practicanteId"), str) for f in grupo):
                return None
            filas.extend(grupo)
        return value if filas else None
    except ValueError:
        return None


@router.get("/auditoria/pagina")
def auditoria_pagina(categoria: str = "TODAS", q: str = "", limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Bitácora por páginas, de la más reciente a la más antigua; nombres de asistencia resueltos en el servidor."""
    _solo_admin(current_user)
    _limite(limite)
    if categoria not in ("TODAS", "ASISTENCIA", "HORAS", "ADMIN"):
        raise HTTPException(422, "Selecciona toda la actividad, asistencia, horas o administración.")
    q = _search(q)
    query = db.query(Auditoria)
    if categoria == "ASISTENCIA":
        query = query.filter(Auditoria.accion == "ASISTENCIA_ACADEMICA")
    elif categoria == "HORAS":
        query = query.filter(Auditoria.accion.like("HORAS_%"))
    elif categoria == "ADMIN":
        query = query.filter(Auditoria.accion != "ASISTENCIA_ACADEMICA", Auditoria.accion.notlike("HORAS_%"))
    if q:
        query = query.filter(func.lower(Auditoria.user_nombre + " " + Auditoria.accion + " " + Auditoria.detalle).contains(q, autoescape=True))
    total = query.order_by(None).count()
    scope = hashlib.sha256(f"auditoria:{current_user.id}:{categoria}:{q}".encode()).hexdigest()
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError()
            anchor = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
            if (not isinstance(anchor, list) or len(anchor) != 3 or anchor[0] != scope
                    or not isinstance(anchor[1], str) or len(anchor[1]) > 50
                    or not isinstance(anchor[2], str) or not 1 <= len(anchor[2]) <= 255):
                raise ValueError()
            previa = datetime.fromisoformat(anchor[1]) if anchor[1] else None
        except (ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(422, "La página no corresponde a esta consulta. Actualiza la lista.") from None
        if previa is None:
            query = query.filter(and_(Auditoria.fecha.is_(None), Auditoria.id < anchor[2]))
        else:
            query = query.filter(or_(Auditoria.fecha < previa, and_(Auditoria.fecha == previa, Auditoria.id < anchor[2]),
                Auditoria.fecha.is_(None)))
    rows = query.order_by(Auditoria.fecha.desc().nullslast(), Auditoria.id.desc()).limit(limite + 1).all()
    shown, siguiente = rows[:limite], None
    if len(rows) > limite:
        last = shown[-1]
        siguiente = base64.urlsafe_b64encode(json.dumps([scope, last.fecha.isoformat() if last.fecha else "", last.id],
            separators=(",", ":")).encode()).decode().rstrip("=")
    aulas_ids, alumnos_ids, detalles = set(), set(), {}
    for row in shown:
        parsed = _detalle_asistencia(row)
        detalles[row.id] = parsed
        if parsed:
            aulas_ids.add(parsed["aulaId"])
            alumnos_ids.update(f["practicanteId"] for f in parsed["antes"] + parsed["despues"])
    nombres_aulas = dict(db.query(Aula.id, Aula.nombre).filter(Aula.id.in_(aulas_ids)).all()) if aulas_ids else {}
    nombres_alumnos = dict(db.query(User.id, User.nombres + " " + User.apellidos).filter(User.id.in_(alumnos_ids)).all()) if alumnos_ids else {}
    items = []
    for row in shown:
        parsed = detalles[row.id]
        estudiantes, vistos = [], set()
        if parsed:
            for fila in parsed["antes"] + parsed["despues"]:
                if fila["practicanteId"] not in vistos:
                    vistos.add(fila["practicanteId"])
                    estudiantes.append({"id": fila["practicanteId"], "nombre": nombres_alumnos.get(fila["practicanteId"], "")})
        items.append({"id": row.id, "userNombre": row.user_nombre, "accion": row.accion, "detalle": row.detalle,
            "fecha": row.fecha.isoformat() if row.fecha else "",
            "aulaNombre": nombres_aulas.get(parsed["aulaId"]) if parsed else None,
            "estudiantes": estudiantes})
    return {"items": items, "total": total, "siguiente": siguiente}
