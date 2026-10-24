"""Lecturas acotadas; los permisos y escrituras mantienen su circuito existente."""
import base64
import hashlib
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.models import Anuncio, Archivo, ContenidoArchivo, ForoHilo, ForoMensaje, MensajeDirecto, User
from app.routers.comunicacion import _aula_con_acceso, _peer, _direct, _mensaje, _anuncio
from app.routers.archivos import _verificar_acceso, visible_files, _to_out

router = APIRouter(tags=["lecturas-paginadas"])


def _page(query, model, scope, limit, cursor, pack, pinned=False):
    if not 1 <= limit <= 40:
        raise HTTPException(422, "El tamaño de página debe estar entre 1 y 40.")
    total = query.order_by(None).count()
    scope = hashlib.sha256(scope.encode()).hexdigest()
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError()
            anchor = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
            if (not isinstance(anchor, list) or len(anchor) != 4 or anchor[0] != scope
                    or not isinstance(anchor[1], str) or len(anchor[1]) > 50
                    or not isinstance(anchor[2], str) or not 1 <= len(anchor[2]) <= 255
                    or type(anchor[3]) is not int or anchor[3] not in (0, 1)):
                raise ValueError()
            date, row_id, rank = datetime.fromisoformat(anchor[1]), anchor[2], anchor[3]
        except (ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(422, "La página no corresponde a esta consulta. Actualiza la lista.") from None
        older = or_(model.created_at < date, and_(model.created_at == date, model.id < row_id))
        query = query.filter(or_(model.fijado < rank, and_(model.fijado == rank, older)) if pinned else older)
    order = [model.created_at.desc(), model.id.desc()]
    if pinned:
        order.insert(0, model.fijado.desc())
    rows = query.order_by(*order).limit(limit + 1).all()
    shown = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = shown[-1]
        anchor = [scope, last.created_at.isoformat(), last.id, int(last.fijado) if pinned else 0]
        next_cursor = base64.urlsafe_b64encode(json.dumps(anchor, separators=(',', ':')).encode()).decode().rstrip('=')
    return {"items": [pack(row) for row in shown], "total": total, "siguiente": next_cursor}


@router.get("/aulas/{aula_id}/anuncios/pagina")
def announcements(aula_id: str, fijados: bool = False, limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    query = db.query(Anuncio.id, Anuncio.aula_id, Anuncio.autor_nombre, Anuncio.titulo,
        Anuncio.fijado, Anuncio.created_at, func.substr(Anuncio.mensaje, 1, 180).label('resumen')).filter(Anuncio.aula_id == aula_id)
    if fijados:
        query = query.filter(Anuncio.fijado == 1)
    return _page(query, Anuncio, f'anuncios:{current_user.id}:{aula_id}:{fijados}', limite, cursor,
        lambda row: {"id": row.id, "aulaId": row.aula_id, "titulo": row.titulo, "autorNombre": row.autor_nombre,
                     "fijado": bool(row.fijado), "fecha": row.created_at.isoformat(), "resumen": row.resumen}, pinned=True)


@router.get("/aulas/{aula_id}/anuncios/{anuncio_id}/detalle")
def announcement(aula_id: str, anuncio_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    row = db.query(Anuncio).filter(Anuncio.aula_id == aula_id, Anuncio.id == anuncio_id).first()
    if row is None:
        raise HTTPException(404, "El anuncio no está disponible en esta aula.")
    return _anuncio(row)


def _thread_query(db):
    count = db.query(func.count(ForoMensaje.id)).filter(ForoMensaje.hilo_id == ForoHilo.id).correlate(ForoHilo).scalar_subquery()
    return db.query(ForoHilo.id, ForoHilo.aula_id, ForoHilo.autor_nombre, ForoHilo.titulo, ForoHilo.created_at, count.label('respuestas'))


def _thread_out(row):
    return {"id": row.id, "aulaId": row.aula_id, "autorNombre": row.autor_nombre, "titulo": row.titulo,
            "fecha": row.created_at.isoformat(), "respuestas": row.respuestas}


@router.get("/aulas/{aula_id}/foros/pagina")
def threads(aula_id: str, limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
            db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    return _page(_thread_query(db).filter(ForoHilo.aula_id == aula_id), ForoHilo,
                 f'foros:{current_user.id}:{aula_id}', limite, cursor, _thread_out)


@router.get("/aulas/{aula_id}/foros/{hilo_id}/detalle")
def thread(aula_id: str, hilo_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _aula_con_acceso(aula_id, current_user, db)
    row = _thread_query(db).filter(ForoHilo.aula_id == aula_id, ForoHilo.id == hilo_id).first()
    if row is None:
        raise HTTPException(404, "El tema no está disponible en esta aula.")
    return _thread_out(row)


@router.get("/foros/{hilo_id}/mensajes/pagina")
def forum_messages(hilo_id: str, limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = db.get(ForoHilo, hilo_id)
    if row is None:
        raise HTTPException(404, "Tema no disponible.")
    _aula_con_acceso(row.aula_id, current_user, db)
    return _page(db.query(ForoMensaje).filter(ForoMensaje.hilo_id == hilo_id), ForoMensaje,
                 f'respuestas:{current_user.id}:{hilo_id}', limite, cursor, _mensaje)


@router.get("/aulas/{aula_id}/mensajes/{otro_id}/pagina")
def direct_messages(aula_id: str, otro_id: str, limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    aula = _aula_con_acceso(aula_id, current_user, db)
    _peer(aula, current_user, otro_id, db)
    query = db.query(MensajeDirecto).filter(MensajeDirecto.aula_id == aula_id,
        MensajeDirecto.remitente_id.in_([current_user.id, otro_id]), MensajeDirecto.destinatario_id.in_([current_user.id, otro_id]))
    unread = query.filter(MensajeDirecto.destinatario_id == current_user.id, MensajeDirecto.leido == 0).count()
    result = _page(query.options(joinedload(MensajeDirecto.remitente)), MensajeDirecto,
        f'privado:{current_user.id}:{aula_id}:{otro_id}', limite, cursor, lambda row: _direct(row, current_user))
    result['noLeidos'] = unread
    return result


@router.get("/aulas/{aula_id}/archivos/pagina")
def files(aula_id: str, tipo: str = 'todos', limite: int = Query(20, ge=1, le=40), cursor: str | None = None,
          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _verificar_acceso(aula_id, current_user, db)
    if tipo not in ('todos', 'materiales', 'propios'):
        raise HTTPException(422, "Selecciona todos, materiales o propios.")
    query = visible_files(db, aula_id, current_user)
    if tipo == 'propios':
        query = query.filter(Archivo.subido_por_id == current_user.id)
    if tipo == 'materiales':
        query = query.filter(db.query(ContenidoArchivo.archivo_id).filter(
            ContenidoArchivo.archivo_id == Archivo.id, ContenidoArchivo.material == 1).exists())
    return _page(query.options(joinedload(Archivo.subido_por)), Archivo,
                 f'archivos:{current_user.id}:{aula_id}:{tipo}', limite, cursor, _to_out)
