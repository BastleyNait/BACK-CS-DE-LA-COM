"""Tareas y entregas: pruebas aisladas, sin conexión a Supabase."""
import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import Aula, AulaEstadoEnum, Archivo, Entrega, Inscripcion, RoleEnum, Tarea, User
from app.routers.tareas import create_tarea, list_tareas_docente, submit_entrega
from app.schemas.schemas import CreateTareaRequest, SubmitEntregaRequest


class TaskFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name, role in [('teacher', 'PROFESOR'), ('otherteacher', 'PROFESOR'), ('student', 'ALUMNO'), ('otherstudent', 'ALUMNO'), ('supervisor', 'SUPERVISOR'), ('admin', 'ADMIN')]:
            user = User(id=name, nombres=name, apellidos='Prueba', email=f'{name}@example.org', hashed_password='unused', role=RoleEnum(role))
            self.db.add(user); self.users[name] = user
        for suffix, teacher, student in [('1', 'teacher', 'student'), ('2', 'otherteacher', 'otherstudent')]:
            self.db.add(Aula(id='a'+suffix, nombre='Aula', codigo=suffix, periodo='TEST', profesor_id=teacher))
            self.db.add(Inscripcion(id='i'+suffix, alumno_id=student, aula_id='a'+suffix))
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def payload(self, **kwargs):
        values = dict(titulo='Entrevista', descripcion='Escribe una entrevista.', fechaLimite=datetime.now(timezone.utc)+timedelta(days=1), solicitudId='unit-task-00000001')
        values.update(kwargs)
        return CreateTareaRequest(**values)

    def expect_status(self, code, fn, *args):
        with self.assertRaises(HTTPException) as raised:
            fn(*args)
        self.assertEqual(raised.exception.status_code, code)
        self.db.rollback()

    def create(self, payload=None):
        return create_tarea('a1', payload or self.payload(), self.db, self.users['teacher'])

    def test_publish_idempotency_roles_and_scope(self):
        payload = self.payload()
        first = self.create(payload)
        self.assertEqual(first.id, self.create(payload).id)
        self.assertEqual(self.db.query(Tarea).count(), 1)
        self.expect_status(409, self.create, self.payload(titulo='Otro título'))
        for name, code in [('student', 403), ('supervisor', 403), ('otherteacher', 404)]:
            self.expect_status(code, create_tarea, 'a1', self.payload(), self.db, self.users[name])
            self.expect_status(code, list_tareas_docente, 'a1', self.db, self.users[name])
        self.assertEqual(len(list_tareas_docente('a1', self.db, self.users['admin'])), 1)

    def test_delivery_is_single_and_same_payload_can_repeat_after_deadline(self):
        task = self.create()
        payload = SubmitEntregaRequest(descripcion='Respuesta escrita', comentario='Comentario')
        first = submit_entrega('a1', task.id, payload, self.db, self.users['student'])
        self.db.get(Tarea, task.id).fecha_limite = datetime.now(timezone.utc)-timedelta(days=1)
        self.db.commit()
        second = submit_entrega('a1', task.id, payload, self.db, self.users['student'])
        self.assertEqual(first.entrega.id, second.entrega.id)
        self.assertEqual(self.db.query(Entrega).count(), 1)
        self.expect_status(409, submit_entrega, 'a1', task.id, SubmitEntregaRequest(descripcion='Otra respuesta'), self.db, self.users['student'])
        self.expect_status(403, submit_entrega, 'a1', task.id, payload, self.db, self.users['otherstudent'])
        self.expect_status(403, submit_entrega, 'a1', task.id, payload, self.db, self.users['supervisor'])

    def test_validation_closed_class_and_deadline(self):
        with self.assertRaises(ValidationError): self.payload(titulo='  ')
        with self.assertRaises(ValidationError): self.payload(fechaLimite=datetime.now())
        with self.assertRaises(ValidationError): SubmitEntregaRequest(descripcion='   ')
        self.expect_status(422, self.create, self.payload(fechaLimite=datetime.now(timezone.utc)-timedelta(days=1)))
        task = self.create()
        self.db.get(Tarea, task.id).fecha_limite = datetime.now(timezone.utc)-timedelta(days=1)
        self.db.commit()
        self.expect_status(422, submit_entrega, 'a1', task.id, SubmitEntregaRequest(descripcion='Texto'), self.db, self.users['student'])
        self.db.get(Aula, 'a1').estado = AulaEstadoEnum.CONCLUIDA; self.db.commit()
        self.expect_status(409, self.create, self.payload(solicitudId='unit-task-00000002'))
        self.expect_status(409, submit_entrega, 'a1', task.id, SubmitEntregaRequest(descripcion='Texto'), self.db, self.users['student'])
        self.assertEqual(self.db.query(Entrega).count(), 0)

    def test_attachment_must_belong_to_student_and_class(self):
        task = self.create()
        for key, aula, owner in [('foreign-owner', 'a1', 'otherstudent'), ('foreign-class', 'a2', 'student')]:
            self.db.add(Archivo(id=key, aula_id=aula, subido_por_id=owner, nombre_original='test.pdf', nombre_guardado=key, tipo_mime='application/pdf', tamanio=1))
        self.db.commit()
        for key in ['foreign-owner', 'foreign-class']:
            self.expect_status(404, submit_entrega, 'a1', task.id, SubmitEntregaRequest(descripcion='Texto', archivoId=key), self.db, self.users['student'])
        self.assertEqual(self.db.query(Entrega).count(), 0)


if __name__ == '__main__': unittest.main()
