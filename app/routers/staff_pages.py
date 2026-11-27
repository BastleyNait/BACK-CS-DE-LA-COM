"""Lecturas de personal: páginas en SQL y detalle puntual, sin mutaciones."""
import base64
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload
from app.core.deps import get_current_user
from app.core.practice_access import require_practice, visible_practices
from app.db.session import get_db
from app.models.models import (Aula, CambioTarea, Entrega, Inscripcion, MensajeDirecto, Meta, MetaTipoEnum, Practica, PracticaEstadoEnum,
    RegistroAsistencia, RegistroHoras, RegistroHorasEstadoEnum, Tarea, User, VersionEntrega)
from app.routers.aulas import _aula_to_out
from app.routers.profesor import _solo_profesor_o_admin, _aula_del_profesor
from app.routers.module_pages import _page
from app.routers.comunicacion import _aula_con_acceso
from app.schemas.schemas import EntregaProfesorOut

router = APIRouter(prefix='/equipo', tags=['personal-paginado'])


def _search(value):
    value = value.strip().lower()
    if len(value) > 120:
        raise HTTPException(422, 'La búsqueda admite hasta 120 caracteres.')
    return value


def _name():
    return User.nombres + ' ' + User.apellidos


def _alphabetic(query, sort, identifier, scope, limit, cursor, pack):
    """Orden total por texto e ID; el cursor queda ligado al usuario y filtros."""
    if not 1 <= limit <= 40:
        raise HTTPException(422, 'El tamaño de página debe estar entre 1 y 40.')
    total = query.order_by(None).count()
    scope = hashlib.sha256(scope.encode()).hexdigest()
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError()
            anchor = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
            if (not isinstance(anchor, list) or len(anchor) != 3 or anchor[0] != scope
                    or not isinstance(anchor[1], str) or len(anchor[1]) > 500
                    or not isinstance(anchor[2], str) or not 1 <= len(anchor[2]) <= 255):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(422, 'La página no corresponde a esta consulta. Actualiza la lista.') from None
        query = query.filter(or_(sort > anchor[1], and_(sort == anchor[1], identifier > anchor[2])))
    rows = query.add_columns(sort.label('_orden'), identifier.label('_clave')).order_by(sort, identifier).limit(limit + 1).all()
    shown, next_cursor = rows[:limit], None
    if len(rows) > limit:
        last = shown[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([scope, last._orden, last._clave], separators=(',', ':')).encode()).decode().rstrip('=')
    return {'items': [pack(row) for row in shown], 'total': total, 'siguiente': next_cursor}


@router.get('/aulas/pagina')
def classrooms(q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    q = _search(q)
    query = db.query(Aula.id, Aula.nombre, Aula.codigo, Aula.periodo, Aula.profesor_id,
        Aula.estado, Aula.inscritos, _name().label('docente')).join(User, User.id == Aula.profesor_id)
    if current_user.role.value == 'PROFESOR':
        query = query.filter(Aula.profesor_id == current_user.id)
    if q:
        query = query.filter(func.lower(Aula.nombre + ' ' + Aula.codigo + ' ' + Aula.periodo + ' ' + _name()).contains(q, autoescape=True))
    return _alphabetic(query, func.lower(Aula.nombre), Aula.id, f'aulas:{current_user.id}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'nombre': row.nombre, 'codigo': row.codigo, 'periodo': row.periodo,
            'profesorId': row.profesor_id, 'profesorNombre': row.docente, 'estado': row.estado.value, 'inscritos': row.inscritos})


@router.get('/aulas/{aula_id}')
def classroom(aula_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    aula = _aula_del_profesor(aula_id, current_user, db)
    return _aula_to_out(aula)


def _roster(db, aula_id, q):
    query = db.query(Inscripcion.id, Inscripcion.alumno_id, Inscripcion.progreso,
        Inscripcion.semana_actual, Inscripcion.semanas_totales, User.email, _name().label('nombre'))
    query = query.join(User, User.id == Inscripcion.alumno_id).filter(Inscripcion.aula_id == aula_id)
    if q:
        query = query.filter(func.lower(_name() + ' ' + User.email).contains(q, autoescape=True))
    return query


@router.get('/aulas/{aula_id}/alumnos/pagina')
def students(aula_id: str, q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
             db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    aula = _aula_del_profesor(aula_id, current_user, db)
    q = _search(q)
    tasks = db.query(func.count(Tarea.id)).filter(Tarea.aula_id == aula_id).scalar()
    delivered = db.query(func.count(func.distinct(Entrega.tarea_id))).join(Tarea, Tarea.id == Entrega.tarea_id).filter(
        Tarea.aula_id == aula_id, Entrega.alumno_id == Inscripcion.alumno_id).correlate(Inscripcion).scalar_subquery()
    query = _roster(db, aula_id, q).add_columns(delivered.label('entregadas'))
    return _alphabetic(query, func.lower(User.apellidos + ' ' + User.nombres), Inscripcion.id,
        f'padron:{current_user.id}:{aula_id}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'alumnoId': row.alumno_id, 'alumnoNombre': row.nombre, 'alumnoEmail': row.email,
            'aulaId': aula_id, 'aulaNombre': aula.nombre, 'progreso': row.progreso, 'semanaActual': row.semana_actual,
            'semanasTotales': row.semanas_totales, 'estado': aula.estado.value, 'tareasTotal': tasks, 'tareasEntregadas': row.entregadas})


def _deliveries(db, aula_id):
    return db.query(Entrega.id, Entrega.tarea_id, Entrega.alumno_id, Entrega.created_at,
        Entrega.estado, Entrega.nota, Tarea.titulo, _name().label('nombre')).join(Tarea, Tarea.id == Entrega.tarea_id).join(
        User, User.id == Entrega.alumno_id).filter(Tarea.aula_id == aula_id)


@router.get('/aulas/{aula_id}/entregas/pagina')
def deliveries(aula_id: str, pendientes: bool = True, q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)
    q = _search(q)
    query = _deliveries(db, aula_id)
    if pendientes:
        query = query.filter(Entrega.nota.is_(None))
    if q:
        query = query.filter(func.lower(_name() + ' ' + Tarea.titulo).contains(q, autoescape=True))
    return _page(query, Entrega, f'entregas:{current_user.id}:{aula_id}:{pendientes}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'tareaId': row.tarea_id, 'tareaTitulo': row.titulo, 'alumnoId': row.alumno_id,
            'alumnoNombre': row.nombre, 'createdAt': row.created_at.isoformat(), 'estado': row.estado.value, 'nota': row.nota})


@router.get('/aulas/{aula_id}/entregas/{entrega_id}', response_model=EntregaProfesorOut)
def delivery(aula_id: str, entrega_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)
    row = db.query(Entrega).join(Tarea).options(joinedload(Entrega.alumno), joinedload(Entrega.tarea)).filter(
        Tarea.aula_id == aula_id, Entrega.id == entrega_id).first()
    if row is None:
        raise HTTPException(404, 'La entrega no está disponible en esta aula.')
    revision = db.query(func.coalesce(func.max(VersionEntrega.revision), 0)).filter(VersionEntrega.entrega_id == row.id).scalar()
    return EntregaProfesorOut(id=row.id, revision=revision, tareaId=row.tarea_id, tareaTitulo=row.tarea.titulo,
        alumnoId=row.alumno_id, alumnoNombre=f'{row.alumno.nombres} {row.alumno.apellidos}', descripcion=row.descripcion,
        comentario=row.comentario, archivoId=row.archivo_id, estado=row.estado.value, nota=row.nota,
        retroalimentacion=row.retroalimentacion, createdAt=row.created_at.isoformat())


def _task_revision(db):
    return db.query(func.coalesce(func.max(CambioTarea.revision), 0)).filter(
        CambioTarea.tarea_id == Tarea.id).correlate(Tarea).scalar_subquery()


@router.get('/aulas/{aula_id}/tareas/pagina')
def task_page(aula_id: str, q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
              db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)
    q = _search(q)
    entregas = db.query(func.count(Entrega.id)).filter(Entrega.tarea_id == Tarea.id).correlate(Tarea).scalar_subquery()
    query = db.query(Tarea.id, Tarea.aula_id, Tarea.titulo, Tarea.created_at, Tarea.fecha_limite,
        func.substr(Tarea.descripcion, 1, 180).label('resumen'), _task_revision(db).label('revision'),
        entregas.label('entregas')).filter(Tarea.aula_id == aula_id)
    if q:
        query = query.filter(func.lower(Tarea.titulo).contains(q, autoescape=True))
    return _page(query, Tarea, f'tareas:{current_user.id}:{aula_id}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'aulaId': row.aula_id, 'titulo': row.titulo, 'resumen': row.resumen,
            'createdAt': row.created_at.isoformat(), 'fechaLimite': row.fecha_limite.isoformat() if row.fecha_limite else None,
            'revision': row.revision, 'entregas': row.entregas})


@router.get('/aulas/{aula_id}/tareas/{tarea_id}')
def task_detail(aula_id: str, tarea_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)
    row = db.query(Tarea).filter(Tarea.aula_id == aula_id, Tarea.id == tarea_id).first()
    if row is None:
        raise HTTPException(404, 'La tarea no está disponible en esta aula.')
    revision = db.query(func.coalesce(func.max(CambioTarea.revision), 0)).filter(CambioTarea.tarea_id == row.id).scalar()
    return {'id': row.id, 'aulaId': row.aula_id, 'titulo': row.titulo, 'descripcion': row.descripcion,
        'fechaLimite': row.fecha_limite.isoformat() if row.fecha_limite else None,
        'createdAt': row.created_at.isoformat(), 'revision': revision, 'entrega': None}


@router.get('/aulas/{aula_id}/notas/pagina')
def grades(aula_id: str, q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
           db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _solo_profesor_o_admin(current_user)
    _aula_del_profesor(aula_id, current_user, db)
    q = _search(q)
    averages = db.query(Entrega.alumno_id.label('alumno'), func.avg(Entrega.nota).label('promedio')).join(
        Tarea, Tarea.id == Entrega.tarea_id).filter(Tarea.aula_id == aula_id, Entrega.nota.is_not(None)).group_by(Entrega.alumno_id).subquery()
    roster_ids = select(Inscripcion.alumno_id).where(Inscripcion.aula_id == aula_id)
    general = db.query(func.avg(averages.c.promedio)).filter(averages.c.alumno.in_(roster_ids)).scalar()
    attendance = db.query(func.avg(RegistroAsistencia.presente) * 100).filter(
        RegistroAsistencia.aula_id == aula_id, RegistroAsistencia.practicante_id == Inscripcion.alumno_id).correlate(Inscripcion).scalar_subquery()
    hours = db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).join(Practica, Practica.id == RegistroHoras.practica_id).filter(
        Practica.aula_id == aula_id, Practica.practicante_id == Inscripcion.alumno_id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).correlate(Inscripcion).scalar_subquery()
    query = _roster(db, aula_id, q).outerjoin(averages, averages.c.alumno == Inscripcion.alumno_id).add_columns(
        averages.c.promedio, attendance.label('asistencia'), hours.label('horas'))
    result = _alphabetic(query, func.lower(User.apellidos + ' ' + User.nombres), Inscripcion.id,
        f'notas:{current_user.id}:{aula_id}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'alumnoId': row.alumno_id, 'alumnoNombre': row.nombre, 'aulaId': aula_id,
            'promedio': round(row.promedio, 2) if row.promedio is not None else None,
            'asistenciaPct': round(row.asistencia) if row.asistencia is not None else None, 'horasValidadas': row.horas})
    result['promedioGeneral'] = round(general, 2) if general is not None else None
    return result


def _staff_practice(current_user):
    if current_user.role.value not in ('PROFESOR', 'SUPERVISOR', 'ADMIN'):
        raise HTTPException(403, 'Esta consulta corresponde al personal de prácticas.')


@router.get('/practicas/{practica_id}/metas/pagina')
def goal_page(practica_id: str, estado: str = 'TODAS', q: str = '', limite: int = Query(20, ge=1, le=40),
              cursor: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _staff_practice(current_user)
    require_practice(db, current_user, practica_id)
    if estado not in ('TODAS', 'EN_PROGRESO', 'COMPLETADAS'):
        raise HTTPException(422, 'Selecciona todas, en progreso o completadas.')
    q = _search(q)
    approved = db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(RegistroHoras.practica_id == practica_id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).scalar()
    reached = case((Meta.tipo == MetaTipoEnum.HORAS, approved), else_=Meta.cantidad_alcanzada)
    query = db.query(Meta.id, Meta.practica_id, Meta.tipo, Meta.cantidad_objetivo, Meta.descripcion, Meta.creado_por,
        Meta.created_at, Practica.practicante_id, User.nombres, User.apellidos, reached.label('alcanzada')).join(
        Practica, Practica.id == Meta.practica_id).join(User, User.id == Practica.practicante_id).filter(
        Meta.practica_id == practica_id)
    if estado != 'TODAS':
        query = query.filter(reached >= Meta.cantidad_objetivo if estado == 'COMPLETADAS' else reached < Meta.cantidad_objetivo)
    if q:
        query = query.filter(func.lower(func.coalesce(Meta.descripcion, '')).contains(q, autoescape=True))
    result = _page(query, Meta, f'metas:{current_user.id}:{practica_id}:{estado}:{q}', limite, cursor,
        lambda row: {'id': row.id, 'practicaId': row.practica_id, 'practicanteId': row.practicante_id,
            'practicanteNombre': f'{row.nombres} {row.apellidos}', 'tipo': row.tipo.value,
            'cantidadObjetivo': row.cantidad_objetivo, 'cantidadAlcanzada': row.alcanzada,
            'descripcion': row.descripcion, 'creadoPor': row.creado_por, 'fechaCreacion': row.created_at.isoformat()})
    all_goals = db.query(Meta.id).filter(Meta.practica_id == practica_id)
    result['totalMetas'] = all_goals.count()
    result['completadas'] = all_goals.filter(reached >= Meta.cantidad_objetivo).count()
    return result


def _practice_query(db, current_user):
    approved = db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(RegistroHoras.practica_id == Practica.id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).correlate(Practica).scalar_subquery()
    return visible_practices(db, current_user).with_entities(Practica.id, Practica.practicante_id, Practica.aula_id,
        Practica.periodo, Practica.horas_minimas, Practica.estado, Aula.nombre.label('aula_nombre'), _name().label('nombre'),
        approved.label('aprobadas')).join(User, User.id == Practica.practicante_id).join(Aula, Aula.id == Practica.aula_id)


def _practice_summary(row):
    state = 'CERRADA' if row.estado == PracticaEstadoEnum.CERRADA else 'LISTA_PARA_CIERRE' if row.aprobadas >= row.horas_minimas else 'EN_CURSO'
    return {'id': row.id, 'practicanteId': row.practicante_id, 'practicanteNombre': row.nombre, 'aulaId': row.aula_id,
        'aulaNombre': row.aula_nombre, 'periodo': row.periodo, 'horasAcumuladas': row.aprobadas,
        'horasMinimas': row.horas_minimas, 'estado': state}


@router.get('/practicas/pagina')
def practices(estado: str = 'TODAS', q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
              db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
              aulaId: str = '', alumnoId: str = ''):
    _staff_practice(current_user)
    if estado not in ('TODAS', 'ABIERTAS', 'CERRADAS'):
        raise HTTPException(422, 'Selecciona todas, abiertas o cerradas.')
    if len(aulaId) > 255 or len(alumnoId) > 255:
        raise HTTPException(422, 'El filtro de aula o alumno no es válido.')
    q = _search(q)
    query = _practice_query(db, current_user)
    if aulaId:
        query = query.filter(Practica.aula_id == aulaId)
    if alumnoId:
        query = query.filter(Practica.practicante_id == alumnoId)
    if estado != 'TODAS':
        query = query.filter(Practica.estado == PracticaEstadoEnum.CERRADA if estado == 'CERRADAS' else Practica.estado != PracticaEstadoEnum.CERRADA)
    if q:
        query = query.filter(func.lower(_name() + ' ' + Aula.nombre + ' ' + Practica.periodo).contains(q, autoescape=True))
    return _alphabetic(query, func.lower(User.apellidos + ' ' + User.nombres), Practica.id,
        f'practicas:{current_user.id}:{estado}:{q}:{aulaId}:{alumnoId}', limite, cursor, _practice_summary)


@router.get('/practicas/{practica_id}')
def practice_detail(practica_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _staff_practice(current_user)
    row = _practice_query(db, current_user).filter(Practica.id == practica_id).first()
    if row is None:
        raise HTTPException(404, 'La práctica no está disponible para tu cuenta.')
    return _practice_summary(row)


def _horas_out(r):
    return {'id': r.id, 'practicaId': r.practica_id, 'fecha': r.fecha.isoformat() if r.fecha else None, 'horas': r.horas,
        'descripcion': r.descripcion, 'estadoValidacion': r.estado_validacion.value,
        'revision': r.revision, 'observacion': r.observacion}


@router.get('/practicas/{practica_id}/horas/pagina')
def hours_page(practica_id: str, estado: str = 'TODAS', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Bitácora por páginas con totales globales; la escritura mantiene su circuito."""
    _staff_practice(current_user)
    require_practice(db, current_user, practica_id)
    states = {'TODAS': None, 'PENDIENTES': RegistroHorasEstadoEnum.PENDIENTE,
        'VALIDADAS': RegistroHorasEstadoEnum.VALIDADO, 'RECHAZADAS': RegistroHorasEstadoEnum.RECHAZADO}
    if not 1 <= limite <= 40:
        raise HTTPException(422, 'El tamaño de página debe estar entre 1 y 40.')
    if estado not in states:
        raise HTTPException(422, 'Selecciona todas, pendientes, validadas o rechazadas.')
    query = db.query(RegistroHoras).filter(RegistroHoras.practica_id == practica_id)
    if states[estado] is not None:
        query = query.filter(RegistroHoras.estado_validacion == states[estado])
    total = query.order_by(None).count()
    scope = hashlib.sha256(f'horas:{current_user.id}:{practica_id}:{estado}'.encode()).hexdigest()
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError()
            anchor = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
            if (not isinstance(anchor, list) or len(anchor) != 3 or anchor[0] != scope
                    or not isinstance(anchor[1], str) or len(anchor[1]) > 50
                    or not isinstance(anchor[2], str) or not 1 <= len(anchor[2]) <= 255):
                raise ValueError()
            anterior = datetime.fromisoformat(anchor[1]) if anchor[1] else None
        except (ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(422, 'La página no corresponde a esta consulta. Actualiza la lista.') from None
        if anterior is None:
            query = query.filter(and_(RegistroHoras.fecha.is_(None), RegistroHoras.id < anchor[2]))
        else:
            query = query.filter(or_(RegistroHoras.fecha < anterior,
                and_(RegistroHoras.fecha == anterior, RegistroHoras.id < anchor[2]), RegistroHoras.fecha.is_(None)))
    rows = query.order_by(RegistroHoras.fecha.desc().nullslast(), RegistroHoras.id.desc()).limit(limite + 1).all()
    shown = rows[:limite]
    siguiente = None
    if len(rows) > limite:
        last = shown[-1]
        siguiente = base64.urlsafe_b64encode(json.dumps([scope, last.fecha.isoformat() if last.fecha else '', last.id],
            separators=(',', ':')).encode()).decode().rstrip('=')
    sums = dict(db.query(RegistroHoras.estado_validacion, func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(
        RegistroHoras.practica_id == practica_id).group_by(RegistroHoras.estado_validacion).all())
    return {'items': [_horas_out(row) for row in shown], 'total': total, 'siguiente': siguiente,
        'horasValidadas': sums.get(RegistroHorasEstadoEnum.VALIDADO, 0),
        'horasPendientes': sums.get(RegistroHorasEstadoEnum.PENDIENTE, 0),
        'horasRechazadas': sums.get(RegistroHorasEstadoEnum.RECHAZADO, 0)}


@router.get('/aulas/{aula_id}/contactos/pagina')
def contacts(aula_id: str, q: str = '', sinLeer: bool = False, limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
             db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Contactos del docente responsable: alumnos matriculados, orden alfabético y no leídos en SQL."""
    if current_user.role.value != 'PROFESOR':
        raise HTTPException(403, 'La lista paginada de contactos corresponde al docente responsable.')
    aula = _aula_con_acceso(aula_id, current_user, db)
    q = _search(q)
    unread = db.query(func.count(MensajeDirecto.id)).filter(MensajeDirecto.aula_id == aula_id,
        MensajeDirecto.destinatario_id == current_user.id, MensajeDirecto.remitente_id == User.id,
        MensajeDirecto.leido == 0).correlate(User).scalar_subquery()
    base = db.query(User.id, _name().label('nombre'), unread.label('no_leidos')).join(Inscripcion, Inscripcion.alumno_id == User.id).filter(
        Inscripcion.aula_id == aula_id, User.role == 'ALUMNO')
    total_unread = db.query(func.count(MensajeDirecto.id)).filter(MensajeDirecto.aula_id == aula_id,
        MensajeDirecto.destinatario_id == current_user.id, MensajeDirecto.leido == 0,
        MensajeDirecto.remitente_id.in_(select(Inscripcion.alumno_id).where(Inscripcion.aula_id == aula_id))).scalar()
    query = base
    if q:
        query = query.filter(func.lower(_name() + ' ' + User.email).contains(q, autoescape=True))
    if sinLeer:
        query = query.filter(unread > 0)
    result = _alphabetic(query, func.lower(User.apellidos + ' ' + User.nombres), User.id,
        f'contactos:{current_user.id}:{aula_id}:{q}:{sinLeer}', limite, cursor,
        lambda row: {'userId': row.id, 'nombre': row.nombre, 'aulaId': aula.id, 'aulaNombre': aula.nombre, 'noLeidos': row.no_leidos})
    for item in result['items']:
        item['id'] = item['userId']
    result['noLeidos'] = total_unread
    return result
