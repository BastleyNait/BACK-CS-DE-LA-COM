"""Lecturas de personal: páginas en SQL y detalle puntual, sin mutaciones."""
import base64
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload
from app.core.deps import get_current_user
from app.core.practice_access import visible_practices
from app.db.session import get_db
from app.models.models import (Aula, Entrega, Inscripcion, Practica, PracticaEstadoEnum,
    RegistroAsistencia, RegistroHoras, RegistroHorasEstadoEnum, Tarea, User, VersionEntrega)
from app.routers.aulas import _aula_to_out
from app.routers.profesor import _solo_profesor_o_admin, _aula_del_profesor
from app.routers.module_pages import _page
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


@router.get('/practicas/pagina')
def practices(estado: str = 'TODAS', q: str = '', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
              db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role.value not in ('PROFESOR', 'SUPERVISOR', 'ADMIN'):
        raise HTTPException(403, 'Esta consulta corresponde al personal de prácticas.')
    if estado not in ('TODAS', 'ABIERTAS', 'CERRADAS'):
        raise HTTPException(422, 'Selecciona todas, abiertas o cerradas.')
    q = _search(q)
    approved = db.query(func.coalesce(func.sum(RegistroHoras.horas), 0)).filter(RegistroHoras.practica_id == Practica.id,
        RegistroHoras.estado_validacion == RegistroHorasEstadoEnum.VALIDADO).correlate(Practica).scalar_subquery()
    query = visible_practices(db, current_user).with_entities(Practica.id, Practica.practicante_id, Practica.aula_id,
        Practica.periodo, Practica.horas_minimas, Practica.estado, Aula.nombre.label('aula_nombre'), _name().label('nombre'), approved.label('aprobadas'))
    query = query.join(User, User.id == Practica.practicante_id).join(Aula, Aula.id == Practica.aula_id)
    if estado != 'TODAS':
        query = query.filter(Practica.estado == PracticaEstadoEnum.CERRADA if estado == 'CERRADAS' else Practica.estado != PracticaEstadoEnum.CERRADA)
    if q:
        query = query.filter(func.lower(_name() + ' ' + Aula.nombre + ' ' + Practica.periodo).contains(q, autoescape=True))
    def pack(row):
        state = 'CERRADA' if row.estado == PracticaEstadoEnum.CERRADA else 'LISTA_PARA_CIERRE' if row.aprobadas >= row.horas_minimas else 'EN_CURSO'
        return {'id': row.id, 'practicanteId': row.practicante_id, 'practicanteNombre': row.nombre, 'aulaId': row.aula_id,
            'aulaNombre': row.aula_nombre, 'periodo': row.periodo, 'horasAcumuladas': row.aprobadas, 'horasMinimas': row.horas_minimas, 'estado': state}
    return _alphabetic(query, func.lower(User.apellidos + ' ' + User.nombres), Practica.id,
        f'practicas:{current_user.id}:{estado}:{q}', limite, cursor, pack)
