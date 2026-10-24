"""Volumen, proyecciones y permisos en SQLite; sin escribir en Supabase."""
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import event
from app.models.models import (Aula, AulaEstadoEnum, Empresa, Entrega, EntregaEstadoEnum, Inscripcion,
    Practica, PracticaEstadoEnum, RegistroAsistencia, RegistroHoras, RegistroHorasEstadoEnum,
    RoleEnum, Supervisor, Tarea, User, VersionEntrega)
from app.routers import staff_pages as pages
import test_direct_messages as fixture


class StaffPagesTests(unittest.TestCase):
    def setUp(self):
        fixture.DirectMessagesTests.setUp(self)
        supervisor = User(id='supervisor', nombres='Supervisor', apellidos='Prueba', email='supervisor@unsa.edu.pe', hashed_password='unused', role=RoleEnum.SUPERVISOR)
        self.db.add(supervisor); self.users['supervisor'] = supervisor
        self.db.add(Aula(id='foreign', nombre='Ajena', codigo='FOREIGN', periodo='TEST', profesor_id='otherteacher'))
        self.db.add(Empresa(id='company', razon_social='Centro de prueba', practicante_id='student', ruc='TEST-COMPANY'))
        self.db.add(Supervisor(id='sup', empresa_id='company', user_id='supervisor', nombres='Supervisor', apellidos='Prueba'))
        self.db.commit()

    tearDown = fixture.DirectMessagesTests.tearDown

    def call(self, fn, *args, role='teacher', **kwargs):
        return fn(*args, db=self.db, current_user=self.users[role], **kwargs)

    def denied(self, status, fn, *args, **kwargs):
        with self.assertRaises(HTTPException) as failure:
            self.call(fn, *args, **kwargs)
        self.assertEqual(failure.exception.status_code, status)

    def all_pages(self, fn):
        first = fn(None); second = fn(first['siguiente']); last = fn(second['siguiente'])
        self.assertEqual([len(p['items']) for p in [first, second, last]], [20, 20, 5])
        self.assertEqual([p['total'] for p in [first, second, last]], [45, 45, 45])
        self.assertIsNone(last['siguiente'])
        items = [row for page in [first, second, last] for row in page['items']]
        self.assertEqual(len({row['id'] for row in items}), 45)
        return items

    def roster(self):
        self.db.query(Inscripcion).delete()
        for i in range(45):
            key = f'{i:03}'
            self.db.add(User(id='u' + key, nombres='Mismo', apellidos='Apellido', email=key + '@unsa.edu.pe', hashed_password='unused', role=RoleEnum.ALUMNO))
            self.db.add(Inscripcion(id='i' + key, aula_id='a', alumno_id='u' + key))
        self.db.add(Tarea(id='task', aula_id='a', titulo='Informe', descripcion='Instrucciones' * 1000))
        self.db.add(Tarea(id='task2', aula_id='a', titulo='Informe 2'))
        self.db.commit()

    def practice_rows(self):
        self.roster()
        for i in range(45):
            key = f'{i:03}'
            self.db.add(Practica(id='p' + key, practicante_id='u' + key, aula_id='a', empresa_id='company', periodo='TEST', horas_minimas=4, horas_acumuladas=999,
                estado=PracticaEstadoEnum.CERRADA if i < 7 else PracticaEstadoEnum.EN_CURSO))
        self.db.add(RegistroHoras(id='approved', practica_id='p010', horas=4, descripcion='Validada', estado_validacion=RegistroHorasEstadoEnum.VALIDADO))
        self.db.add(RegistroHoras(id='pending', practica_id='p010', horas=9, descripcion='Pendiente', estado_validacion=RegistroHorasEstadoEnum.PENDIENTE))
        self.db.add(RegistroHoras(id='rejected', practica_id='p010', horas=6, descripcion='Rechazada', estado_validacion=RegistroHorasEstadoEnum.RECHAZADO))
        self.db.commit()

    def test_classroom_pages_ties_literal_search_and_exact_detail(self):
        for i in range(45):
            key = f'{i:03}'
            self.db.add(Aula(id='a' + key, nombre='Gemela', codigo='G' + key, periodo='TEST', profesor_id='teacher', descripcion='Texto' * 1000))
        self.db.flush(); self.db.get(Aula, 'a000').codigo = 'G%000'; self.db.commit()
        items = self.all_pages(lambda cursor: self.call(pages.classrooms, 'gemela', 20, cursor))
        self.assertEqual([row['id'] for row in items], [f'a{i:03}' for i in range(45)])
        self.assertNotIn('descripcion', items[0])
        self.assertEqual(self.call(pages.classrooms, '%', 20, None)['total'], 1)
        self.assertEqual(len(self.call(pages.classroom, 'a000').descripcion), 5000)
        self.denied(403, pages.classroom, 'foreign')
        self.denied(403, pages.classrooms, '', 20, None, role='student')
        self.assertEqual(self.call(pages.classrooms, '', 20, None, role='admin')['total'], 47)

    def test_roster_only_requested_class_and_sql_task_counts(self):
        self.roster()
        for task in ['task', 'task2']:
            self.db.add(Entrega(tarea_id=task, alumno_id='u000'))
        self.db.add(Tarea(id='foreign-task', aula_id='foreign', titulo='Ajena'))
        self.db.add(Entrega(tarea_id='foreign-task', alumno_id='u000')); self.db.commit()
        items = self.all_pages(lambda cursor: self.call(pages.students, 'a', '', 20, cursor))
        self.assertEqual(items[0]['tareasEntregadas'], 2)
        self.assertTrue(all(row['tareasTotal'] == 2 and row['aulaId'] == 'a' for row in items))
        self.assertEqual(self.call(pages.students, 'a', '000@', 20, None)['total'], 1)
        self.denied(403, pages.students, 'foreign', '', 20, None)

    def test_delivery_pages_exclude_bodies_and_exact_detail_max_revision(self):
        self.roster()
        date = datetime(2026, 10, 24, tzinfo=timezone.utc)
        for i in range(45):
            key = f'{i:03}'
            self.db.add(Entrega(id='e' + key, tarea_id='task', alumno_id='u' + key, descripcion='Entrega' * 1000, created_at=date))
        self.db.add(VersionEntrega(id='v1', entrega_id='e000', revision=1, contenido='historial' * 1000, motivo='Primera'))
        self.db.add(VersionEntrega(id='v2', entrega_id='e000', revision=2, contenido='historial' * 1000, motivo='Reemplazo'))
        self.db.commit(); self.db.expunge_all()
        self.users = {key: self.db.get(User, key) for key in self.users}
        items = self.all_pages(lambda cursor: self.call(pages.deliveries, 'a', True, '', 20, cursor))
        self.assertEqual(items[0]['id'], 'e044')
        self.assertTrue(all('descripcion' not in row and 'comentario' not in row for row in items))
        queries = []
        def capture(_conn, _cursor, statement, _params, _ctx, _many): queries.append(statement)
        event.listen(self.engine, 'before_cursor_execute', capture)
        detail = self.call(pages.delivery, 'a', 'e000')
        event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertEqual(detail.revision, 2); self.assertEqual(len(detail.descripcion), 7000)
        self.assertFalse(any('versiones_entregas.contenido' in query for query in queries))
        self.assertFalse(any(isinstance(obj, VersionEntrega) for obj in self.db.identity_map.values()))
        self.denied(404, pages.delivery, 'foreign', 'e000', role='admin')
        self.db.get(Entrega, 'e000').nota = 0; self.db.get(Entrega, 'e000').estado = EntregaEstadoEnum.CALIFICADA; self.db.commit()
        self.assertEqual(self.call(pages.deliveries, 'a', True, '', 20, None)['total'], 44)
        self.assertEqual(self.call(pages.deliveries, 'a', False, '', 20, None)['total'], 45)
        self.assertEqual(self.call(pages.delivery, 'a', 'e000').nota, 0)

    def test_grade_summary_global_average_zero_attendance_and_validated_hours(self):
        self.roster()
        self.db.get(User, 'u000').nombres = 'Cero'
        for task, user, grade in [('task', 'u000', 0), ('task2', 'u000', 10), ('task', 'u001', 20), ('task', 'outsider', 20)]:
            self.db.add(Entrega(tarea_id=task, alumno_id=user, nota=grade))
        for day, present in [(1, 1), (2, 0)]:
            self.db.add(RegistroAsistencia(aula_id='a', practicante_id='u000', fecha=datetime(2026, 10, day), presente=present))
        self.db.add(Practica(id='p', practicante_id='u000', aula_id='a', periodo='TEST', horas_acumuladas=999))
        for key, state, hours in [('ok', RegistroHorasEstadoEnum.VALIDADO, 4), ('pending', RegistroHorasEstadoEnum.PENDIENTE, 9)]:
            self.db.add(RegistroHoras(id=key, practica_id='p', horas=hours, descripcion='Prueba', estado_validacion=state))
        self.db.commit()
        self.all_pages(lambda cursor: self.call(pages.grades, 'a', '', 20, cursor))
        result = self.call(pages.grades, 'a', 'cero', 20, None)
        self.assertEqual(result['total'], 1); self.assertEqual(result['promedioGeneral'], 12.5)
        self.assertEqual(result['items'][0]['promedio'], 5)
        self.assertEqual(result['items'][0]['asistenciaPct'], 50)
        self.assertEqual(result['items'][0]['horasValidadas'], 4)
        self.db.query(Entrega).filter(Entrega.alumno_id == 'u000', Entrega.tarea_id == 'task2').delete(); self.db.commit()
        self.assertEqual(self.call(pages.grades, 'a', 'cero', 20, None)['items'][0]['promedio'], 0)

    def test_practice_pages_supervisor_scope_hours_and_reassignment(self):
        self.practice_rows()
        self.db.expunge_all(); self.users = {key: self.db.get(User, key) for key in self.users}
        items = self.all_pages(lambda cursor: self.call(pages.practices, 'TODAS', '', 20, cursor, role='supervisor'))
        self.assertFalse(any(isinstance(row, RegistroHoras) for row in self.db.identity_map.values()))
        self.assertEqual(items[10]['horasAcumuladas'], 4); self.assertEqual(items[10]['estado'], 'LISTA_PARA_CIERRE')
        self.assertEqual(items[0]['estado'], 'CERRADA')
        self.assertEqual(self.call(pages.practices, 'ABIERTAS', '', 20, None)['total'], 38)
        self.assertEqual(self.call(pages.practices, 'CERRADAS', '', 20, None)['total'], 7)
        self.assertEqual(self.call(pages.practices, 'TODAS', '', 20, None, role='otherteacher')['total'], 0)
        self.db.get(Supervisor, 'sup').user_id = None; self.db.commit()
        self.assertEqual(self.call(pages.practices, 'TODAS', '', 20, None, role='supervisor')['total'], 0)
        self.denied(403, pages.practices, 'TODAS', '', 20, None, role='student')

    def test_cursor_scopes_filters_roles_resource_and_validation(self):
        self.practice_rows()
        cursor = self.call(pages.students, 'a', '', 20, None)['siguiente']
        self.denied(422, pages.students, 'a', 'Mismo', 20, cursor)
        self.denied(422, pages.students, 'a', '', 20, cursor, role='admin')
        self.denied(422, pages.grades, 'a', '', 20, cursor)
        for value in ['invalid', 'x' * 2050, base64_cursor()]:
            self.denied(422, pages.students, 'a', '', 20, value)
        self.denied(422, pages.students, 'a', '', 0, None)
        self.denied(422, pages.practices, 'INVALID', '', 20, None)
        self.denied(422, pages.classrooms, 'x' * 121, 20, None)
        self.db.get(Aula, 'a').profesor_id = 'otherteacher'; self.db.commit()
        self.denied(403, pages.students, 'a', '', 20, cursor)


def base64_cursor():
    import base64
    return base64.urlsafe_b64encode(b'{"bad":"shape"}').decode()


if __name__ == '__main__':
    unittest.main()
