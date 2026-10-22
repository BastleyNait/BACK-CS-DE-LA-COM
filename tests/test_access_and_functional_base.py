"""Pruebas focales del incremento 19: SQLite, correo y Google aislados."""
import io
import zipfile
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import patch
from fastapi import HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials
from starlette.datastructures import Headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import (User, RoleEnum, Aula, Inscripcion, Empresa, Supervisor, Practica,
    RecuperacionCuenta, IdentidadGoogle, Archivo, ContenidoArchivo, VersionEntrega, CambioTarea)
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.core.deps import get_current_user
from app.core.practice_access import require_practice
from app.routers import auth, asignaciones, archivos, tareas, profesor
from app.schemas.schemas import LoginRequest, RecoverRequest, SubmitEntregaRequest, CalificarEntregaRequest


class FunctionalBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'ClaveFicticia-2026'
        cls.password_hash = hash_password(cls.password)

    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name, role in [('alumno', 'ALUMNO'), ('otro', 'ALUMNO'), ('docente', 'PROFESOR'), ('ajeno', 'PROFESOR'), ('supervisor', 'SUPERVISOR'), ('nuevo', 'SUPERVISOR'), ('admin', 'ADMIN')]:
            u = User(id=name, nombres=name, apellidos='Prueba', email=f'{name}@unsa.edu.pe', role=RoleEnum(role), hashed_password=self.password_hash)
            self.users[name] = u
            self.db.add(u)
        self.db.add(Aula(id='a', nombre='Aula', codigo='BASE19', periodo='2026', profesor_id='docente'))
        for name in ['alumno', 'otro']:
            self.db.add(Inscripcion(id=f'i-{name}', alumno_id=name, aula_id='a'))
            self.db.add(Empresa(id=f'e-{name}', practicante_id=name, razon_social='Centro '+name, ruc='00000000000'))
        self.db.add(Supervisor(id='s', empresa_id='e-alumno', user_id='supervisor', nombres='Supervisor', apellidos='Prueba'))
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def expect(self, code, fn, *args):
        with self.assertRaises(HTTPException) as caught: fn(*args)
        self.assertEqual(caught.exception.status_code, code)
        self.db.rollback()

    def assignment(self, **changes):
        return asignaciones.AsignarPracticaRequest(**{'alumnoId': 'alumno', 'aulaId': 'a', 'empresaId': 'e-alumno', 'horasMinimas': 100, 'motivo': 'Criterio ficticio de prueba', 'solicitudId': 'asignacion-ficticia-000001', **changes})

    def task(self, **changes):
        body = tareas.CreateTareaRequest(**{'titulo': 'Informe', 'descripcion': 'Instrucciones de prueba', 'solicitudId': 'tarea-ficticia-000001', **changes})
        return tareas.create_tarea('a', body, self.db, self.users['docente'])

    def upload(self, name='informe.pdf', data=b'%PDF-1.4\nContenido ficticio\n%%EOF', who='alumno', operation='carga-ficticia-000001', mime='application/pdf'):
        file = UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({'content-type': mime}))
        return archivos.upload_archivo('a', file, operation, self.db, self.users[who])

    def test_password_session_me_and_invalid_login(self):
        session = auth.login(LoginRequest(email='alumno@unsa.edu.pe', password=self.password), self.db)
        user = get_current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=session.token), self.db)
        self.assertEqual(auth.me(user).id, 'alumno')
        self.expect(401, auth.login, LoginRequest(email='alumno@unsa.edu.pe', password='incorrecta'), self.db)

    def test_google_checks_verified_domain_audience_and_expiry(self):
        valid = {'aud': 'client-prueba', 'iss': 'https://accounts.google.com', 'sub': 'subject-19', 'hd': 'unsa.edu.pe', 'email': 'alumno@unsa.edu.pe', 'email_verified': True}
        with patch.object(settings, 'GOOGLE_CLIENT_IDS', 'client-prueba'), patch('google.oauth2.id_token.verify_oauth2_token') as verifier:
            verifier.return_value = valid
            self.assertEqual(auth.verify_google('token-ficticio')['sub'], 'subject-19')
            for change, code in [({'hd': ''}, 403), ({'email': 'alumno@gmail.com'}, 403), ({'email_verified': False}, 403), ({'aud': 'otra-app'}, 401)]:
                verifier.return_value = {**valid, **change}
                self.expect(code, auth.verify_google, 'token-ficticio')
            verifier.side_effect = ValueError('Expired token')
            self.expect(401, auth.verify_google, 'token-ficticio')
        with patch.object(settings, 'GOOGLE_CLIENT_IDS', ''):
            self.expect(503, auth.verify_google, 'token-ficticio')

    def test_google_links_existing_account_without_changing_role(self):
        claims = {'sub': 'docente-subject', 'email': 'docente@unsa.edu.pe', 'given_name': 'Otro nombre'}
        with patch.object(auth, 'verify_google', return_value=claims):
            self.expect(428, auth.google_login, auth.GoogleRequest(idToken='token-ficticio'), self.db)
            self.expect(401, auth.google_login, auth.GoogleRequest(idToken='token-ficticio', passwordSsp='incorrecta'), self.db)
            first = auth.google_login(auth.GoogleRequest(idToken='token-ficticio', passwordSsp=self.password), self.db)
            again = auth.google_login(auth.GoogleRequest(idToken='token-ficticio'), self.db)
        self.assertEqual(first.user.role, 'PROFESOR')
        self.assertEqual(first.user.id, again.user.id)
        self.assertEqual(self.db.query(IdentidadGoogle).count(), 1)

    def test_google_new_account_has_only_student_role(self):
        claims = {'sub': 'nuevo-subject', 'email': 'nueva.cuenta@unsa.edu.pe', 'given_name': 'Nueva', 'family_name': 'Cuenta', 'role': 'ADMIN'}
        with patch.object(auth, 'verify_google', return_value=claims):
            result = auth.google_login(auth.GoogleRequest(idToken='token-ficticio'), self.db)
        self.assertEqual(result.user.role, 'ALUMNO')
        self.assertEqual(result.user.nombres, 'Nueva')

    def test_reset_is_one_use_and_revokes_previous_sessions(self):
        previous = auth.login(LoginRequest(email='alumno@unsa.edu.pe', password=self.password), self.db)
        code = 'x'*43
        self.db.add(RecuperacionCuenta(digest=sha256(code.encode()).hexdigest(), user_id='alumno', vence=datetime.now(timezone.utc)+timedelta(minutes=10)))
        self.db.commit()
        body = auth.ResetRequest(codigo=code, password='NuevaFicticia-2026')
        auth.reset_password(body, self.db)
        self.assertTrue(verify_password(body.password, self.db.get(User, 'alumno').hashed_password))
        self.expect(422, auth.reset_password, body, self.db)
        self.expect(401, get_current_user, HTTPAuthorizationCredentials(scheme='Bearer', credentials=previous.token), self.db)

    def test_recovery_does_not_claim_delivery_without_smtp(self):
        with patch.object(settings, 'SMTP_HOST', ''):
            self.expect(503, auth.recover, RecoverRequest(email='alumno@unsa.edu.pe'), self.db)
        code = 'expired-code-'+'x'*32
        self.db.add(RecuperacionCuenta(digest=sha256(code.encode()).hexdigest(), user_id='alumno', vence=datetime.now(timezone.utc)-timedelta(seconds=1)))
        self.db.commit()
        self.expect(422, auth.reset_password, auth.ResetRequest(codigo=code, password='NuevaFicticia-2026'), self.db)

    def test_assignment_requires_admin_enrollment_and_own_center(self):
        self.expect(403, asignaciones.asignar_practica, self.assignment(), self.db, self.users['docente'])
        self.expect(422, asignaciones.asignar_practica, self.assignment(empresaId='e-otro'), self.db, self.users['admin'])
        self.db.query(Inscripcion).filter(Inscripcion.alumno_id == 'alumno').delete(); self.db.commit()
        self.expect(422, asignaciones.asignar_practica, self.assignment(), self.db, self.users['admin'])

    def test_assignment_retries_do_not_duplicate_and_prevent_second_open_practice(self):
        first = asignaciones.asignar_practica(self.assignment(), self.db, self.users['admin'])
        second = asignaciones.asignar_practica(self.assignment(), self.db, self.users['admin'])
        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(Practica).count(), 1)
        self.expect(409, asignaciones.asignar_practica, self.assignment(solicitudId='otra-asignacion-000001'), self.db, self.users['admin'])

    def test_supervisor_reassignment_revokes_old_access_and_supports_many_centers(self):
        practice = asignaciones.asignar_practica(self.assignment(), self.db, self.users['admin'])
        body = asignaciones.VincularSupervisorRequest(userId='nuevo', anterior='supervisor', motivo='Cambio de supervisor autorizado')
        asignaciones.vincular_supervisor('e-alumno', body, self.db, self.users['admin'])
        self.expect(404, require_practice, self.db, self.users['supervisor'], practice.id)
        self.assertEqual(require_practice(self.db, self.users['nuevo'], practice.id).id, practice.id)
        asignaciones.vincular_supervisor('e-otro', asignaciones.VincularSupervisorRequest(userId='nuevo', motivo='Segundo centro autorizado'), self.db, self.users['admin'])
        self.assertEqual(self.db.query(Supervisor).filter(Supervisor.user_id == 'nuevo').count(), 2)
        self.db.get(Practica, practice.id).estado = 'CERRADA'; self.db.commit()
        self.expect(409, asignaciones.vincular_supervisor, 'e-alumno', asignaciones.VincularSupervisorRequest(userId='supervisor', anterior='nuevo', motivo='No cambiar expediente cerrado'), self.db, self.users['admin'])

    def test_supervisor_account_creation_is_idempotent_and_never_escalates_public_role(self):
        body = asignaciones.CrearSupervisorRequest(nombres='Externo', apellidos='Prueba', email='externo@example.org', password=self.password, solicitudId='supervisor-ficticio-000001')
        first = asignaciones.crear_supervisor(body, self.db, self.users['admin'])
        second = asignaciones.crear_supervisor(body, self.db, self.users['admin'])
        self.assertEqual(first.id, second.id); self.assertEqual(first.role, 'SUPERVISOR')
        self.expect(403, asignaciones.crear_supervisor, body, self.db, self.users['alumno'])

    def test_documents_are_private_persistent_and_idempotent(self):
        uploaded = self.upload()
        self.assertEqual(self.upload().id, uploaded.id)
        self.assertEqual(self.db.query(ContenidoArchivo).count(), 1)
        self.expect(404, archivos.descargar_archivo, 'a', uploaded.id, self.db, self.users['otro'])
        self.assertEqual(archivos.list_archivos('a', self.db, self.users['otro']), [])
        self.db.close(); self.db = sessionmaker(bind=self.engine, autoflush=False)()
        response = archivos.descargar_archivo('a', uploaded.id, self.db, self.db.get(User, 'docente'))
        self.assertTrue(response.body.startswith(b'%PDF-'))
        self.assertEqual(response.headers['cache-control'], 'private, no-store')

    def test_document_type_size_archive_traversal_and_wrong_mime(self):
        self.expect(422, self.upload, 'falso.pdf', b'no es PDF')
        self.expect(422, self.upload, 'script.exe', b'MZ...')
        self.expect(422, self.upload, 'informe.pdf', b'%PDF-1.4\n%%EOF', 'alumno', 'otra-carga-000000001', 'text/html')
        self.expect(413, self.upload, 'grande.pdf', b'x'*(archivos.MAX_FILE_SIZE+1))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive: archive.writestr('../escape.txt', 'No permitido')
        self.expect(422, self.upload, 'riesgo.zip', buffer.getvalue(), 'alumno', 'otra-carga-000000002', 'application/zip')

    def test_private_upload_stays_private_after_uploader_role_changes(self):
        private = self.upload()
        self.db.get(User, 'alumno').role = RoleEnum.PROFESOR
        self.db.commit()
        self.expect(404, archivos.descargar_archivo, 'a', private.id, self.db, self.users['otro'])
        material = self.upload(who='docente', operation='material-docente-0000001')
        self.assertEqual([f.id for f in archivos.list_archivos('a', self.db, self.users['otro'])], [material.id])

    def test_delivery_replacement_keeps_history_and_prevents_stale_grading(self):
        task = self.task()
        attachment = self.upload()
        first = tareas.submit_entrega('a', task.id, SubmitEntregaRequest(descripcion='Respuesta inicial', archivoId=attachment.id), self.db, self.users['alumno'])
        self.assertEqual(first.entrega.revision, 0)
        body = tareas.ReemplazarEntregaRequest(descripcion='Respuesta corregida', revision=0, motivo='Mejora del documento')
        saved = tareas.reemplazar_entrega('a', task.id, body, self.db, self.users['alumno'])
        self.assertEqual(saved.entrega.revision, 1)
        self.assertEqual(tareas.reemplazar_entrega('a', task.id, body, self.db, self.users['alumno']).entrega.revision, 1)
        self.assertEqual(self.db.query(VersionEntrega).count(), 2)
        self.expect(409, profesor.calificar_entrega, saved.entrega.id, CalificarEntregaRequest(nota=15, revisionEntrega=0), self.db, self.users['docente'])
        profesor.calificar_entrega(saved.entrega.id, CalificarEntregaRequest(nota=15, revisionEntrega=1), self.db, self.users['docente'])
        self.expect(409, tareas.reemplazar_entrega, 'a', task.id, tareas.ReemplazarEntregaRequest(descripcion='Otra respuesta', revision=1, motivo='Intento posterior a nota'), self.db, self.users['alumno'])
        self.expect(409, archivos.eliminar_archivo, 'a', attachment.id, self.db, self.users['alumno'])

    def test_expired_task_requires_teacher_extension_and_tracks_changes(self):
        task = self.task()
        row = self.db.get(tareas.Tarea, task.id); row.fecha_limite = datetime.now(timezone.utc)-timedelta(days=1); self.db.commit()
        self.expect(422, tareas.submit_entrega, 'a', task.id, SubmitEntregaRequest(descripcion='Respuesta'), self.db, self.users['alumno'])
        body = tareas.EditarTareaRequest(titulo='Informe', descripcion='Instrucciones actualizadas', fechaLimite=datetime.now(timezone.utc)+timedelta(days=2), solicitudId='edicion-ficticia-000001', revision=0, motivo='Ampliación de plazo autorizada')
        self.expect(404, tareas.editar_tarea, 'a', task.id, body, self.db, self.users['ajeno'])
        updated = tareas.editar_tarea('a', task.id, body, self.db, self.users['docente'])
        self.assertEqual(updated.revision, 1)
        self.assertEqual(self.db.query(CambioTarea).count(), 1)
        self.assertEqual(tareas.editar_tarea('a', task.id, body, self.db, self.users['docente']).revision, 1)
        tareas.submit_entrega('a', task.id, SubmitEntregaRequest(descripcion='Respuesta'), self.db, self.users['alumno'])

    def test_closed_practice_rejects_new_files_and_replacements(self):
        practice = asignaciones.asignar_practica(self.assignment(), self.db, self.users['admin'])
        task = self.task()
        tareas.submit_entrega('a', task.id, SubmitEntregaRequest(descripcion='Respuesta original'), self.db, self.users['alumno'])
        self.db.get(Practica, practice.id).estado = 'CERRADA'; self.db.commit()
        self.expect(409, self.upload)
        self.expect(409, tareas.reemplazar_entrega, 'a', task.id, tareas.ReemplazarEntregaRequest(descripcion='Cambiar después del cierre', revision=0, motivo='Intento no permitido'), self.db, self.users['alumno'])
