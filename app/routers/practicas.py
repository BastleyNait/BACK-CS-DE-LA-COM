"""
Ciclo de prácticas: seguimiento de horas (HU-14), cierre y validación docente
(HU-15), historial por practicante (HU-18) y reporte final (HU-16).
Rutas: /api/v1/practicas/*
"""

import uuid
from datetime import datetime, timezone, timedelta, time, date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.practice_access import require_practice, visible_practices, sync_hours
from app.db.session import get_db
from app.models.models import (
    Aula,
    Empresa,
    Practica,
    PracticaEstadoEnum,
    RegistroHoras,
    RegistroHorasEstadoEnum,
    Supervisor,
    User,
)
from app.schemas.schemas import (
    PracticaOut,
    RegistrarHorasRequest,
    RegistrarHorasResponse,
    RegistroHorasOut,
    ReporteFinalOut,
    UserOut,
)

router = APIRouter(prefix="/practicas", tags=["practicas"])


def _to_practica_out(p: Practica) -> PracticaOut:
    aprobadas = sum(r.horas for r in p.registros_horas if r.estado_validacion == RegistroHorasEstadoEnum.VALIDADO)
    estado = p.estado if p.estado == PracticaEstadoEnum.CERRADA else (PracticaEstadoEnum.LISTA_PARA_CIERRE if aprobadas >= p.horas_minimas else PracticaEstadoEnum.EN_CURSO)
    return PracticaOut(
        id=p.id,
        practicanteId=p.practicante_id,
        practicanteNombre=f"{p.practicante.nombres} {p.practicante.apellidos}",
        aulaId=p.aula_id,
        aulaNombre=p.aula.nombre,
        periodo=p.periodo,
        empresaId=p.empresa_id,
        horasAcumuladas=aprobadas,
        horasMinimas=p.horas_minimas,
        estado=estado.value,
        fechaInicio=p.fecha_inicio.isoformat() if p.fecha_inicio else "",
        fechaCierre=p.fecha_cierre.isoformat() if p.fecha_cierre else None,
        validadoPor=p.validado_por,
    )


def _to_registro_out(r: RegistroHoras) -> RegistroHorasOut:
    return RegistroHorasOut(
        id=r.id,
        practicaId=r.practica_id,
        fecha=r.fecha.isoformat() if r.fecha else "",
        horas=r.horas,
        descripcion=r.descripcion,
        estadoValidacion=r.estado_validacion.value,
    )


def _practicas_visibles(db: Session, user: User) -> list[Practica]:
    return visible_practices(db, user).all()


# ── GET /api/v1/practicas ─────────────────────────────────────────────────────


@router.get("/capacidades")
def capacidades(current_user: User = Depends(get_current_user)):
    return {"versionHoras": 1}


@router.get("", response_model=list[PracticaOut])
def list_practicas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Prácticas visibles para el usuario según su rol."""
    practicas = _practicas_visibles(db, current_user)
    practicas.sort(key=lambda p: p.fecha_inicio or datetime.min, reverse=True)
    return [_to_practica_out(p) for p in practicas]


# ── GET /api/v1/practicas/actual ──────────────────────────────────────────────


@router.get("/actual", response_model=PracticaOut | None)
def get_actual(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Práctica activa (o más reciente) del practicante autenticado."""
    mias = (
        db.query(Practica)
        .filter(Practica.practicante_id == current_user.id)
        .all()
    )
    if not mias:
        return None
    activa = next(
        (p for p in mias if p.estado != PracticaEstadoEnum.CERRADA), None
    )
    if activa is None:
        mias.sort(key=lambda p: p.fecha_inicio or datetime.min, reverse=True)
        activa = mias[0]
    return _to_practica_out(activa)


# ── GET /api/v1/practicas/por-aula/{aula_id} ──────────────────────────────────


@router.get("/por-aula/{aula_id}", response_model=PracticaOut | None)
def get_por_aula(
    aula_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Práctica del practicante autenticado en un aula concreta (bitácora HU-14)."""
    practica = (
        db.query(Practica)
        .filter(
            Practica.practicante_id == current_user.id,
            Practica.aula_id == aula_id,
        )
        .first()
    )
    return _to_practica_out(practica) if practica else None


# ── GET /api/v1/practicas/practicantes ────────────────────────────────────────


@router.get("/practicantes", response_model=list[UserOut])
def list_practicantes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Practicantes con al menos un ciclo registrado (HU-18)."""
    if current_user.role.value == "ALUMNO":
        raise HTTPException(status_code=403, detail="Acceso restringido.")
    practicas = _practicas_visibles(db, current_user)
    vistos: dict[str, User] = {}
    for p in practicas:
        if p.practicante_id not in vistos:
            vistos[p.practicante_id] = p.practicante
    alumnos = sorted(vistos.values(), key=lambda u: (u.apellidos, u.nombres))
    return alumnos


# ── GET /api/v1/practicas/historial/{practicante_id} ──────────────────────────


@router.get("/historial/{practicante_id}", response_model=list[PracticaOut])
def historial(
    practicante_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historial completo de ciclos de prácticas de un practicante (HU-18)."""
    if current_user.role.value == "ALUMNO" and current_user.id != practicante_id:
        raise HTTPException(status_code=403, detail="Acceso restringido.")
    registros = (
        visible_practices(db, current_user)
        .filter(Practica.practicante_id == practicante_id)
        .all()
    )
    registros.sort(key=lambda p: p.fecha_inicio or datetime.min, reverse=True)
    return [_to_practica_out(p) for p in registros]


# ── GET /api/v1/practicas/{practica_id}/horas ─────────────────────────────────


@router.get("/{practica_id}/horas", response_model=list[RegistroHorasOut])
def get_horas(
    practica_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bitácora de horas registradas para una práctica (HU-14)."""
    require_practice(db, current_user, practica_id)
    registros = (
        db.query(RegistroHoras)
        .filter(RegistroHoras.practica_id == practica_id)
        .all()
    )
    registros.sort(key=lambda r: r.fecha or datetime.min, reverse=True)
    return [_to_registro_out(r) for r in registros]


# ── POST /api/v1/practicas/{practica_id}/horas ────────────────────────────────


@router.post(
    "/{practica_id}/horas",
    response_model=RegistrarHorasResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_horas(
    practica_id: str,
    payload: RegistrarHorasRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra una nueva entrada de horas trabajadas (HU-14)."""
    if current_user.role.value != "ALUMNO":
        raise HTTPException(403, "Solo el alumno registra sus horas.")
    practica = require_practice(db, current_user, practica_id, lock=True)
    lima = timezone(timedelta(hours=-5))
    day = datetime.now(lima).date()
    if payload.fecha:
        try:
            if len(payload.fecha) == 10:
                day = date.fromisoformat(payload.fecha)
            else:
                parsed = datetime.fromisoformat(payload.fecha.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError()
                day = parsed.astimezone(lima).date()
        except ValueError:
            raise HTTPException(422, "Fecha inválida. Usa AAAA-MM-DD.")
    if day > datetime.now(lima).date():
        raise HTTPException(422, "No puedes registrar actividades futuras.")
    fecha = datetime.combine(day, time(12), tzinfo=lima).astimezone(timezone.utc)
    registro_id = "h-" + payload.solicitudId if payload.solicitudId else "h-" + uuid.uuid4().hex
    existente = db.get(RegistroHoras, registro_id)
    if existente:
        existing_day = existente.fecha.replace(tzinfo=timezone.utc) if existente.fecha.tzinfo is None else existente.fecha
        if (existente.practica_id != practica_id or existente.horas != payload.horas
                or existente.descripcion != payload.descripcion or existing_day != fecha):
            raise HTTPException(409, "La solicitud ya se usó con otros datos.")
        return RegistrarHorasResponse(practica=_to_practica_out(practica), registro=_to_registro_out(existente))
    if practica.estado == PracticaEstadoEnum.CERRADA:
        raise HTTPException(409, "La práctica está cerrada.")
    registro = RegistroHoras(id=registro_id, practica_id=practica_id, fecha=fecha,
                             horas=payload.horas, descripcion=payload.descripcion,
                             estado_validacion=RegistroHorasEstadoEnum.PENDIENTE)
    db.add(registro)
    sync_hours(db, practica)
    db.commit()
    return RegistrarHorasResponse(practica=_to_practica_out(practica), registro=_to_registro_out(registro))


# ── POST /api/v1/practicas/{practica_id}/cerrar ───────────────────────────────


@router.post("/{practica_id}/cerrar", response_model=PracticaOut)
def cerrar_practica(
    practica_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cierra y valida formalmente una práctica (HU-15). Solo docente/admin."""
    if current_user.role.value not in {"PROFESOR", "ADMIN"}:
        raise HTTPException(403, "Solo el docente responsable o administración puede cerrar la práctica.")
    practica = require_practice(db, current_user, practica_id, lock=True)
    sync_hours(db, practica)
    if practica.estado == PracticaEstadoEnum.CERRADA:
        raise HTTPException(
            status_code=409, detail="Esta práctica ya se encuentra cerrada."
        )
    if practica.horas_acumuladas < practica.horas_minimas:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Aún no cumple el mínimo de horas "
                f"({practica.horas_acumuladas}/{practica.horas_minimas})."
            ),
        )
    if not practica.empresa_id:
        raise HTTPException(
            status_code=422,
            detail="El practicante no ha registrado su empresa de prácticas.",
        )

    practica.estado = PracticaEstadoEnum.CERRADA
    practica.fecha_cierre = datetime.now(timezone.utc)
    practica.validado_por = f"{current_user.nombres} {current_user.apellidos}"
    db.commit()
    db.refresh(practica)
    return _to_practica_out(practica)


# ── POST /api/v1/practicas/{practica_id}/reporte ──────────────────────────────


def _fmt_fecha(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


@router.post("/{practica_id}/reporte", response_model=ReporteFinalOut)
def generar_reporte(
    practica_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Genera el reporte final consolidado de una práctica (HU-16)."""
    practica = require_practice(db, current_user, practica_id)

    empresa = (
        db.query(Empresa).filter(Empresa.id == practica.empresa_id).first()
        if practica.empresa_id
        else None
    )
    supervisor = (
        db.query(Supervisor).filter(Supervisor.empresa_id == empresa.id).first()
        if empresa
        else None
    )
    horas = (
        db.query(RegistroHoras)
        .filter(RegistroHoras.practica_id == practica_id)
        .all()
    )
    horas.sort(key=lambda r: r.fecha or datetime.min, reverse=True)

    cerrada = practica.estado == PracticaEstadoEnum.CERRADA
    lineas = [
        "REPORTE FINAL DE PRÁCTICAS PRE-PROFESIONALES",
        "Escuela Profesional de Ciencias de la Comunicación — UNSA",
        "",
        f"Practicante: {practica.practicante.nombres} {practica.practicante.apellidos}",
        f"Aula / práctica: {practica.aula.nombre} ({practica.periodo})",
        f"Estado: {'Cerrada y validada' if cerrada else 'En curso'}",
        (
            f"Horas acumuladas: {practica.horas_acumuladas} / "
            f"{practica.horas_minimas} (mín. reglamentario RCU 0501-2020)"
        ),
        "",
        (
            f"Empresa / centro de prácticas: "
            f"{empresa.razon_social if empresa else 'No registrada'}"
        ),
    ]
    if empresa:
        lineas.append(f"RUC: {empresa.ruc} — {empresa.direccion}")
    if supervisor:
        lineas.append(
            f"Supervisor externo: {supervisor.nombres} {supervisor.apellidos} "
            f"({supervisor.cargo}) — {supervisor.email}"
        )
    else:
        lineas.append("Supervisor externo: No registrado")
    lineas += [
        "",
        f"Bitácora de horas ({len(horas)} registro(s)):",
        *[
            f"  • {_fmt_fecha(h.fecha)} — {h.horas}h — {h.descripcion}"
            for h in horas
        ],
        "",
        (
            f"Validado por: {practica.validado_por} el {_fmt_fecha(practica.fecha_cierre)}"
            if practica.validado_por
            else "Pendiente de validación docente."
        ),
        "",
        (
            f"Generado por: {current_user.nombres} {current_user.apellidos} "
            f"el {_fmt_fecha(datetime.now(timezone.utc))}"
        ),
    ]

    contenido = "\n".join(lineas)
    return ReporteFinalOut(
        id=f"r-{uuid.uuid4().hex[:10]}",
        practicaId=practica_id,
        generadoPor=f"{current_user.nombres} {current_user.apellidos}",
        generadoEn=datetime.now(timezone.utc).isoformat(),
        contenido=contenido,
    )
