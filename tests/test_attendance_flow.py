"""Padrón, estado guardado y concurrencia optimista; base SQLite aislada."""
import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import Auditoria, Aula, AulaEstadoEnum, Inscripcion, RegistroAsistencia, RoleEnum, User
from app.routers.profesor import get_asistencia, guardar_asistencia, historial_asistencia
from app.routers.admin import matricular, desmatricular
from app.schemas.schemas import GuardarAsistenciaRequest, MatricularRequest


class AttendanceFlowTests(unittest.TestCase):
    day = '2026-01-15'
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name, role in [('teacher', 'PROFESOR'), ('otherteacher', 'PROFESOR'), ('admin', 'ADMIN'), ('supervisor', 'SUPERVISOR'), ('s1', 'ALUMNO'), ('s2', 'ALUMNO'), ('s3', 'ALUMNO')]:
            u = User(id=name, nombres=name, apellidos='Prueba', email=f'{name}@example.org', hashed_password='unused', role=RoleEnum(role))
            self.db.add(u); self.users[name] = u
        self.db.add(Aula(id='a1', nombre='Aula', codigo='A1', periodo='TEST', profesor_id='teacher', inscritos=2))
        for name in ['s1', 's2']: self.db.add(Inscripcion(alumno_id=name, aula_id='a1'))
        self.db.commit()

    def tearDown(self): self.db.close(); self.engine.dispose()
    def read(self, day=None): return get_asistencia('a1', day or self.day, self.db, self.users['teacher'])
    def payload(self, base, values=None):
        values = values or {i.practicanteId: i.presente for i in base.items}
        return GuardarAsistenciaRequest(fecha=base.fecha, revision=base.revision, items=[{'practicanteId': k, 'presente': v} for k, v in values.items()])
    def save(self, payload): return guardar_asistencia('a1', payload, self.db, self.users['teacher'])
    def audits(self): return self.db.query(Auditoria).filter(Auditoria.accion == 'ASISTENCIA_ACADEMICA').all()
    def expect_status(self, code, fn, *args):
        with self.assertRaises(HTTPException) as raised: fn(*args)
        self.assertEqual(raised.exception.status_code, code); self.db.rollback()

    def test_proposed_then_saved_and_repeated_request_has_one_audit(self):
        initial = self.read()
        self.assertEqual(initial.estadoRegistro, 'PROPUESTO')
        self.assertTrue(all(not i.registrado for i in initial.items))
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 0)
        payload = self.payload(initial)
        saved = self.save(payload)
        self.assertEqual(saved.estadoRegistro, 'GUARDADO')
        self.assertTrue(all(i.registrado for i in saved.items))
        self.assertNotEqual(saved.revision, initial.revision)
        self.assertEqual(self.save(payload).revision, saved.revision)
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 2)
        audit = self.audits(); self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].user_id, 'teacher')
        self.assertEqual(json.loads(audit[0].detalle)['antes'], [])
        self.assertEqual(len(json.loads(audit[0].detalle)['despues']), 2)

    def test_invalid_rosters_and_non_boolean_do_not_write(self):
        base = self.read()
        for ids in [[], ['s1'], ['s1', 's1'], ['s1', 's3']]:
            payload = GuardarAsistenciaRequest(fecha=self.day, revision=base.revision, items=[{'practicanteId': i, 'presente': True} for i in ids])
            self.expect_status(409, self.save, payload)
        with self.assertRaises(ValidationError): GuardarAsistenciaRequest(fecha=self.day, revision=base.revision, items=[{'practicanteId': 's1', 'presente': 1}])
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 0)
        self.assertEqual(len(self.audits()), 0)

    def test_stale_edit_cannot_overwrite_and_fresh_edit_can(self):
        base = self.read()
        first = self.save(self.payload(base, {'s1': True, 's2': False}))
        self.expect_status(409, self.save, self.payload(base, {'s1': False, 's2': True}))
        self.assertEqual({i.practicanteId: i.presente for i in self.read().items}, {'s1': True, 's2': False})
        fresh = self.save(self.payload(first, {'s1': False, 's2': True}))
        self.assertNotEqual(fresh.revision, first.revision)
        self.assertEqual(len(self.audits()), 2)
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 2)

    def test_enrollment_change_requires_current_roster_and_marks_partial(self):
        base = self.read()
        matricular('a1', MatricularRequest(alumnoId='s3'), self.db, self.users['admin'])
        self.expect_status(409, self.save, self.payload(base))
        partial = self.save(self.payload(self.read()))
        self.assertEqual(partial.estadoRegistro, 'GUARDADO')
        desmatricular('a1', 's3', self.db, self.users['admin'])
        current = self.read(); self.assertEqual(current.estadoRegistro, 'GUARDADO')
        self.save(self.payload(current, {'s1': False, 's2': True}))
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 3)
        self.assertEqual(self.db.query(RegistroAsistencia).filter(RegistroAsistencia.practicante_id == 's3').count(), 1)

    def test_dates_permissions_and_closed_class(self):
        for value in ['2026-02-30', '2026-01-15T00:00:00Z', '2026-1-15', '20260115']:
            self.expect_status(422, self.read, value)
        future = (datetime.now(timezone(timedelta(hours=-5))).date()+timedelta(days=1)).isoformat()
        self.expect_status(422, self.save, self.payload(self.read(future)))
        for name, status in [('s1', 403), ('supervisor', 403), ('otherteacher', 403)]:
            self.expect_status(status, get_asistencia, 'a1', self.day, self.db, self.users[name])
            self.expect_status(status, guardar_asistencia, 'a1', self.payload(self.read()), self.db, self.users[name])
        self.db.get(Aula, 'a1').estado = AulaEstadoEnum.CONCLUIDA; self.db.commit()
        self.expect_status(409, self.save, self.payload(self.read()))
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 0)

    def test_partial_old_rows_are_normalized_and_preserved_in_audit(self):
        date = datetime(2026, 1, 15, tzinfo=timezone.utc)
        for key, user, present in [('r1', 's1', 0), ('r2', 's1', 1), ('r3', 's3', 1)]:
            self.db.add(RegistroAsistencia(id=key, aula_id='a1', practicante_id=user, fecha=date, presente=present))
        self.db.add(Inscripcion(alumno_id='s1', aula_id='a1'))  # matrícula histórica duplicada
        self.db.commit()
        current = self.read()
        self.assertEqual(current.estadoRegistro, 'PARCIAL')
        self.assertEqual(len(current.items), 2)
        self.assertEqual([i.practicanteId for i in current.items if not i.registrado], ['s2'])
        saved = self.save(self.payload(current))
        self.assertEqual(saved.estadoRegistro, 'GUARDADO')
        self.assertEqual(self.db.query(RegistroAsistencia).count(), 3)
        audit = json.loads(self.audits()[0].detalle)
        self.assertEqual(len(audit['antes']), 2)
        self.assertEqual(audit['conservadosFueraDelPadron'], ['r3'])

    def history(self, limite=20, cursor=None, user='teacher'): return historial_asistencia('a1', limite, cursor, self.db, self.users[user])

    def test_history_lists_only_saved_days_most_recent_first(self):
        self.assertEqual(self.history(), {'items': [], 'total': 0, 'siguiente': None})
        self.read()  # consultar sin guardar no crea registro ni entra al historial
        self.assertEqual(self.history()['total'], 0)
        self.save(self.payload(self.read(), {'s1': True, 's2': False}))
        second = self.save(self.payload(self.read('2026-01-14')))
        page = self.history()
        self.assertEqual(page['total'], 2)
        self.assertEqual(page['siguiente'], None)
        self.assertEqual([row['fecha'] for row in page['items']], ['2026-01-15', '2026-01-14'])
        self.assertEqual(page['items'][0], {'fecha': '2026-01-15', 'presentes': 1, 'registrados': 2})
        self.assertEqual(page['items'][1], {'fecha': '2026-01-14', 'presentes': 2, 'registrados': 2})
        # Repetir el guardado idéntico no duplica el día del historial.
        self.save(second)
        self.assertEqual(self.history()['total'], 2)

    def test_history_pages_by_cursor_and_checks_scope_and_roles(self):
        self.save(self.payload(self.read()))
        self.save(self.payload(self.read('2026-01-14')))
        first = self.history(limite=1)
        self.assertEqual([row['fecha'] for row in first['items']], ['2026-01-15'])
        self.assertEqual(first['total'], 2)
        self.assertNotEqual(first['siguiente'], None)
        second = self.history(limite=1, cursor=first['siguiente'])
        self.assertEqual([row['fecha'] for row in second['items']], ['2026-01-14'])
        self.assertEqual(second['siguiente'], None)
        self.expect_status(422, self.history, 20, 'cursor-falso')
        forged = base64.urlsafe_b64encode(json.dumps(['otro-alcance', '2026-01-15T00:00:00+00:00'], separators=(',', ':')).encode()).decode().rstrip('=')
        self.expect_status(422, self.history, 20, forged)
        self.expect_status(403, self.history, 20, None, 'supervisor')
        self.expect_status(403, self.history, 20, None, 's1')
        self.expect_status(403, self.history, 20, None, 'otherteacher')
        # Administración consulta el historial del aula del docente.
        self.assertEqual(self.history(user='admin')['total'], 2)


if __name__ == '__main__': unittest.main()
