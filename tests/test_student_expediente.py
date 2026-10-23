"""Resumen del alumno: mismo criterio, permisos y copia cerrada sin historial."""
import json
import unittest
from sqlalchemy import event
from fastapi import HTTPException
from app.core.expediente import student_summary
from app.models.models import ExpedientePractica, RegistroHoras, Tarea
from app.routers.expedientes import get_student_summary, cerrar_expediente
from app.schemas.expediente import CerrarExpedienteRequest
import test_expediente_flow as flow


class StudentExpedienteTests(unittest.TestCase):
    setUp = flow.ExpedienteFlowTests.setUp
    tearDown = flow.ExpedienteFlowTests.tearDown
    get = flow.ExpedienteFlowTests.get
    requirements = flow.ExpedienteFlowTests.requirements
    assessment = flow.ExpedienteFlowTests.assessment
    complete = flow.ExpedienteFlowTests.complete

    def summary(self):
        return get_student_summary('p', self.db, self.users['alumno'])

    def test_same_requirements_and_totals_without_loading_hour_records(self):
        self.complete()
        for i in range(45):
            self.db.add(RegistroHoras(id=f'pending-{i}', practica_id='p', horas=8,
                descripcion='Actividad pendiente de revisión', estado_validacion='PENDIENTE'))
            self.db.add(Tarea(id=f'optional-{i}', aula_id='a', titulo='Tarea adicional', descripcion='x' * 2000))
        self.db.commit()
        expected = student_summary(self.get())
        self.db.expunge_all()
        statements = []
        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement)
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            actual = self.summary()
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertEqual(actual, expected)
        self.assertEqual(actual['practica']['horasValidadas'], 2)
        self.assertFalse(any(isinstance(row, RegistroHoras) for row in self.db.identity_map.values()))
        hour_queries = [sql for sql in statements if 'FROM registro_horas' in sql]
        self.assertEqual(len(hour_queries), 1)
        self.assertIn('sum(', hour_queries[0])
        self.assertNotIn('horas', actual)
        self.assertNotIn('tareas', actual)
        self.assertNotIn('metas', actual)
        self.assertNotIn('revision', actual)
        self.assertNotIn('tareas', actual['configuracion'])

    def test_empty_configuration_and_missing_requirements_keep_same_result(self):
        self.assertEqual(self.summary(), student_summary(self.get()))
        self.assertEqual(self.summary()['practica']['horasValidadas'], 0)
        self.complete()
        row = self.db.get(ExpedientePractica, 'p')
        values = json.loads(row.requisitos)
        values['tareas'].append('missing-task')
        values['metas'].append('missing-goal')
        row.requisitos = json.dumps(values)
        self.db.commit()
        result = self.summary()
        self.assertEqual(result, student_summary(self.get()))
        self.assertFalse(result['puedeCerrar'])
        self.assertFalse(next(item for item in result['checklist'] if item['id'] == 'tareas')['cumplido'])
        self.assertFalse(next(item for item in result['checklist'] if item['id'] == 'metas')['cumplido'])

    def test_closed_summary_projects_frozen_snapshot(self):
        current = self.complete()
        saved = cerrar_expediente('p', CerrarExpedienteRequest(revision=current['revision'], motivo='Cierre de prueba revisado'), self.db, self.users['docente'])
        self.db.get(RegistroHoras, 'h').horas = 100
        self.db.get(Tarea, 't').titulo = 'No debe cambiar el expediente cerrado'
        self.db.commit()
        self.assertEqual(self.summary(), student_summary(saved))
        self.assertEqual(self.summary()['practica']['horasValidadas'], 2)

    def test_restricted_role_and_practice_ownership(self):
        for who, status in [('otro', 404), ('docente', 403), ('admin', 403), ('supervisor', 403)]:
            with self.assertRaises(HTTPException) as result:
                get_student_summary('p', self.db, self.users[who])
            self.assertEqual(result.exception.status_code, status)
        with self.assertRaises(HTTPException) as result:
            get_student_summary('missing', self.db, self.users['alumno'])
        self.assertEqual(result.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
