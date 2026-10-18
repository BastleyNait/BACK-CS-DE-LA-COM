"""Pruebas finales del expediente con SQLite aislado, sin escrituras en Supabase."""
import json
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import (Auditoria, Aula, Empresa, Entrega, ExpedientePractica, Inscripcion, Meta,
    Practica, PracticaEstadoEnum, RegistroHoras, RoleEnum, Supervisor, Tarea, User)
from app.routers.expedientes import get_expediente, guardar_requisitos, guardar_evaluacion, cerrar_expediente, descargar_pdf
from app.routers.practicas import cerrar_practica, generar_reporte
from app.schemas.expediente import RequisitosRequest, EvaluacionRequest, CerrarExpedienteRequest


class ExpedienteFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for key, role in [('alumno', 'ALUMNO'), ('otro', 'ALUMNO'), ('docente', 'PROFESOR'), ('ajeno', 'PROFESOR'), ('supervisor', 'SUPERVISOR'), ('externo', 'SUPERVISOR'), ('admin', 'ADMIN')]:
            user = User(id=key, nombres=key, apellidos='Prueba', email=key+'@example.org', hashed_password='unused', role=RoleEnum(role))
            self.users[key] = user
            self.db.add(user)
        self.db.add(Aula(id='a', nombre='Aula de prueba', codigo='EXP', periodo='2026', profesor_id='docente'))
        self.db.add(Empresa(id='e', practicante_id='alumno', razon_social='Centro ficticio', ruc='00000000000'))
        self.db.add(Supervisor(id='s', empresa_id='e', user_id='supervisor', nombres='Supervisión', apellidos='Prueba'))
        self.db.add(Inscripcion(id='i', alumno_id='alumno', aula_id='a'))
        self.db.add(Practica(id='p', practicante_id='alumno', aula_id='a', empresa_id='e', periodo='2026', horas_minimas=2))
        self.db.add(Tarea(id='t', aula_id='a', titulo='Informe final'))
        self.db.add(Meta(id='m', practica_id='p', tipo='ARTICULOS', cantidad_objetivo=1, cantidad_alcanzada=0, creado_por='docente'))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def get(self, who='alumno'):
        return get_expediente('p', self.db, self.users[who])

    def expect_status(self, code, fn, *args):
        with self.assertRaises(HTTPException) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status_code, code)
        self.db.rollback()

    def requirements(self, **changes):
        return RequisitosRequest(**{'revision': 0, 'tareas': ['t'], 'metas': ['m'], 'notaMinima': 11, 'motivo': 'Requisitos acordados para la práctica', **changes})

    def assessment(self, **changes):
        return EvaluacionRequest(**{'revision': 0, 'desempeno': 'Cumple con las actividades revisadas.', 'fortalezas': 'Redacción clara y verificada.', 'mejoras': 'Continuar con revisión de fuentes.', 'conclusion': 'FAVORABLE', 'conformidad': True, **changes})

    def complete(self):
        guardar_requisitos('p', self.requirements(), self.db, self.users['docente'])
        guardar_evaluacion('p', self.assessment(), self.db, self.users['supervisor'])
        self.db.add(RegistroHoras(id='h', practica_id='p', horas=2, descripcion='Entrevista y edición', estado_validacion='VALIDADO'))
        self.db.add(Entrega(id='ent', tarea_id='t', alumno_id='alumno', nota=15, estado='CALIFICADA', retroalimentacion='Buen trabajo.'))
        self.db.get(Meta, 'm').cantidad_alcanzada = 1
        self.db.commit()
        return self.get('docente')

    def test_checklist_requires_explicit_configuration_and_favorable_assessment(self):
        data = self.get()
        self.assertFalse(data['puedeCerrar'])
        self.assertIsNone(data['configuracion'])
        self.expect_status(422, cerrar_expediente, 'p', CerrarExpedienteRequest(revision=data['revision'], motivo='Revisado por docente'), self.db, self.users['docente'])
        guardar_requisitos('p', self.requirements(tareas=[], metas=[]), self.db, self.users['docente'])
        guardar_evaluacion('p', self.assessment(conclusion='REQUIERE_MEJORAS'), self.db, self.users['supervisor'])
        self.assertFalse(next(c for c in self.get()['checklist'] if c['id'] == 'evaluacion')['cumplido'])

    def test_roles_and_practice_ownership(self):
        for who in ['otro', 'ajeno', 'externo']:
            self.expect_status(404, get_expediente, 'p', self.db, self.users[who])
        for who in ['alumno', 'docente', 'admin']:
            self.expect_status(403, guardar_evaluacion, 'p', self.assessment(), self.db, self.users[who])
        self.expect_status(403, guardar_requisitos, 'p', self.requirements(), self.db, self.users['supervisor'])
        data = self.get()
        self.expect_status(403, cerrar_expediente, 'p', CerrarExpedienteRequest(revision=data['revision'], motivo='Sin autorización'), self.db, self.users['alumno'])
        self.expect_status(409, cerrar_practica, 'p', self.db, self.users['docente'])

    def test_requirements_validate_scope_revision_and_idempotence(self):
        self.expect_status(422, guardar_requisitos, 'p', self.requirements(tareas=['ajena']), self.db, self.users['docente'])
        first = guardar_requisitos('p', self.requirements(), self.db, self.users['docente'])
        again = guardar_requisitos('p', self.requirements(), self.db, self.users['docente'])
        self.assertEqual(first, again)
        self.assertEqual(self.db.query(Auditoria).count(), 1)
        self.expect_status(409, guardar_requisitos, 'p', self.requirements(notaMinima=12), self.db, self.users['docente'])

    def test_assessment_retries_updates_and_current_supervisor(self):
        for _ in range(2):
            guardar_evaluacion('p', self.assessment(), self.db, self.users['supervisor'])
        self.assertEqual(self.get()['evaluacion']['revision'], 1)
        self.assertEqual(self.db.query(Auditoria).count(), 1)
        self.expect_status(409, guardar_evaluacion, 'p', self.assessment(desempeno='Otro desempeño distinto.'), self.db, self.users['supervisor'])
        guardar_evaluacion('p', self.assessment(revision=1, conclusion='REQUIERE_MEJORAS'), self.db, self.users['supervisor'])
        self.db.get(Supervisor, 's').user_id = 'externo'
        self.db.commit()
        self.assertFalse(self.get()['evaluacionVigente'])
        self.expect_status(404, guardar_evaluacion, 'p', self.assessment(revision=2), self.db, self.users['supervisor'])

    def test_closure_snapshot_retry_and_mutation_guards(self):
        data = self.complete()
        self.assertTrue(data['puedeCerrar'])
        payload = CerrarExpedienteRequest(revision=data['revision'], motivo='Expediente completo revisado por docente')
        closed = cerrar_expediente('p', payload, self.db, self.users['docente'])
        self.assertTrue(closed['cerrado'])
        self.assertEqual(closed['cierre']['version'], 1)
        self.assertEqual(cerrar_expediente('p', payload, self.db, self.users['docente']), closed)
        self.assertEqual(self.db.query(Auditoria).filter(Auditoria.accion == 'PRACTICA_CERRADA').count(), 1)
        self.db.get(Tarea, 't').titulo = 'Cambio posterior ajeno a la copia'
        self.db.commit()
        self.assertEqual(self.get(), closed)
        self.assertIn('Informe final', generar_reporte('p', self.db, self.users['alumno']).contenido)
        self.expect_status(409, guardar_evaluacion, 'p', self.assessment(revision=1), self.db, self.users['supervisor'])
        self.expect_status(409, guardar_requisitos, 'p', self.requirements(revision=1), self.db, self.users['docente'])

    def test_stale_data_and_pending_grades_block_closure(self):
        data = self.complete()
        self.db.get(Entrega, 'ent').nota = 5
        self.db.commit()
        self.expect_status(409, cerrar_expediente, 'p', CerrarExpedienteRequest(revision=data['revision'], motivo='Intento con versión antigua'), self.db, self.users['docente'])
        updated = self.get()
        self.assertFalse(updated['puedeCerrar'])
        self.expect_status(422, cerrar_expediente, 'p', CerrarExpedienteRequest(revision=updated['revision'], motivo='Intento con nota pendiente'), self.db, self.users['docente'])

    def test_pdf_escapes_markup_and_is_private(self):
        self.complete()
        self.db.get(Tarea, 't').titulo = '<b>Prueba & texto</b>'
        self.db.commit()
        response = descargar_pdf('p', self.db, self.users['alumno'])
        self.assertTrue(response.body.startswith(b'%PDF-'))
        self.assertEqual(response.media_type, 'application/pdf')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.expect_status(404, descargar_pdf, 'p', self.db, self.users['otro'])

    def test_input_validation(self):
        for change in [{'revision': True}, {'conformidad': 1}, {'conformidad': False}, {'conclusion': 'APROBADO'}, {'desempeno': ' '}]:
            with self.assertRaises(ValidationError):
                self.assessment(**change)
        for change in [{'notaMinima': 21}, {'tareas': ['t', 't']}, {'revision': -1}]:
            with self.assertRaises(ValidationError):
                self.requirements(**change)
