"""Circuitos de anuncios/foros/metas con SQLite aislado."""
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, AulaEstadoEnum, Inscripcion, Practica, PracticaEstadoEnum, Meta, RegistroHoras, RegistroHorasEstadoEnum, Auditoria, Anuncio, ForoHilo, ForoMensaje
from app.routers.comunicacion import aulas_comunicacion, crear_anuncio, list_anuncios, crear_hilo, list_hilos, responder_hilo, list_mensajes_hilo
from app.routers.metas import create_meta, establecer_avance, list_by_practicante, list_by_practica, registrar_avance
from app.schemas.schemas import CreateAnuncioRequest, CreateHiloRequest, CreateForoMensajeRequest, CreateMetaRequest, EstablecerAvanceMetaRequest, RegistrarAvanceMetaRequest


class CommunityModulesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name, role in [('teacher', 'PROFESOR'), ('teacher2', 'PROFESOR'), ('student', 'ALUMNO'), ('student2', 'ALUMNO'), ('supervisor', 'SUPERVISOR'), ('admin', 'ADMIN')]:
            u = User(id=name, nombres=name, apellidos='Prueba', email=f'{name}@example.org', hashed_password='unused', role=RoleEnum(role))
            self.db.add(u); self.users[name] = u
        for suffix in ['', '2']:
            self.db.add(Aula(id='a'+suffix, nombre='Aula'+suffix, codigo='A'+suffix, periodo='TEST', profesor_id='teacher'+suffix))
            self.db.add(Inscripcion(alumno_id='student'+suffix, aula_id='a'+suffix))
            self.db.add(Practica(id='p'+suffix, practicante_id='student'+suffix, aula_id='a'+suffix, periodo='TEST', horas_acumuladas=999))
        self.db.commit()

    def tearDown(self): self.db.close(); self.engine.dispose()
    def expect_status(self, code, fn, *args):
        with self.assertRaises(HTTPException) as raised: fn(*args)
        self.assertEqual(raised.exception.status_code, code); self.db.rollback()
    def announcement(self, key='announcement-00000001'):
        return crear_anuncio('a', CreateAnuncioRequest(titulo='Aviso de revisión', mensaje='Preparar el resumen', fijado=True, solicitudId=key), self.db, self.users['teacher'])
    def thread(self):
        return crear_hilo('a', CreateHiloRequest(titulo='Dudas del reportaje', solicitudId='thread-000000000001'), self.db, self.users['student'])
    def goal(self, kind='ARTICULOS', key='goal-00000000000001'):
        return create_meta('p', CreateMetaRequest(tipo=kind, cantidadObjetivo=4, descripcion='Producción revisada', solicitudId=key), self.db, self.users['teacher'])

    def test_announcement_permissions_scoped_list_and_pinning(self):
        one = self.announcement()
        self.assertTrue(list_anuncios('a', self.db, self.users['student'])[0].fijado)
        self.assertEqual([a['id'] for a in aulas_comunicacion(self.db, self.users['student'])], ['a'])
        for name in ['student', 'supervisor', 'teacher2']:
            self.expect_status(403, crear_anuncio, 'a', CreateAnuncioRequest(titulo='Aviso', mensaje='Texto'), self.db, self.users[name])
        self.expect_status(403, list_anuncios, 'a', self.db, self.users['student2'])
        self.assertEqual(one.autorNombre, 'teacher Prueba')

    def test_announcement_retry_does_not_duplicate_and_changed_request_conflicts(self):
        one = self.announcement(); self.assertEqual(self.announcement().id, one.id)
        self.expect_status(409, crear_anuncio, 'a', CreateAnuncioRequest(titulo='Otro', mensaje='Preparar el resumen', fijado=True, solicitudId='announcement-00000001'), self.db, self.users['teacher'])
        self.assertEqual(self.db.query(Anuncio).count(), 1); self.assertEqual(self.db.query(Auditoria).count(), 1)

    def test_forum_membership_reply_retry_and_answer_count(self):
        hilo = self.thread(); self.assertEqual(self.thread().id, hilo.id)
        payload = CreateForoMensajeRequest(texto='Revisa las fuentes', solicitudId='reply-0000000000001')
        first = responder_hilo(hilo.id, payload, self.db, self.users['teacher'])
        self.assertEqual(responder_hilo(hilo.id, payload, self.db, self.users['teacher']).id, first.id)
        responder_hilo(hilo.id, CreateForoMensajeRequest(texto='Gracias, lo revisaré'), self.db, self.users['student'])
        self.assertEqual(list_hilos('a', self.db, self.users['student'])[0].respuestas, 2)
        self.assertEqual(len(list_mensajes_hilo(hilo.id, self.db, self.users['teacher'])), 2)
        self.expect_status(403, responder_hilo, hilo.id, payload, self.db, self.users['student2'])
        self.expect_status(403, list_mensajes_hilo, hilo.id, self.db, self.users['teacher2'])
        self.assertEqual(self.db.query(ForoHilo).count(), 1); self.assertEqual(self.db.query(ForoMensaje).count(), 2)

    def test_concluded_class_is_read_only(self):
        self.announcement(); hilo = self.thread()
        self.db.get(Aula, 'a').estado = AulaEstadoEnum.CONCLUIDA; self.db.commit()
        self.assertEqual(len(list_anuncios('a', self.db, self.users['student'])), 1)
        self.expect_status(409, self.announcement, 'announcement-00000002')
        self.expect_status(409, crear_hilo, 'a', CreateHiloRequest(titulo='Nuevo tema'), self.db, self.users['student'])
        self.expect_status(409, responder_hilo, hilo.id, CreateForoMensajeRequest(texto='Respuesta'), self.db, self.users['teacher'])
        self.assertEqual(self.db.query(Auditoria).count(), 2)

    def test_goals_reject_foreign_writes_and_do_not_expose_other_student(self):
        self.goal()
        for name, code in [('student', 403), ('supervisor', 403), ('teacher2', 404)]:
            self.expect_status(code, create_meta, 'p', CreateMetaRequest(tipo='ARTICULOS', cantidadObjetivo=2), self.db, self.users[name])
        self.assertEqual(list_by_practicante('student', self.db, self.users['student2']), [])
        self.assertEqual(list_by_practicante('student', self.db, self.users['teacher2']), [])
        self.expect_status(404, list_by_practica, 'p', self.db, self.users['student2'])

    def test_goal_creation_and_absolute_total_are_idempotent_and_audited(self):
        meta = self.goal(); self.assertEqual(self.goal().id, meta.id)
        payload = EstablecerAvanceMetaRequest(cantidad=2, anterior=0, motivo='Dos notas revisadas')
        for _ in range(2): self.assertEqual(establecer_avance(meta.id, payload, self.db, self.users['teacher']).cantidadAlcanzada, 2)
        self.expect_status(409, establecer_avance, meta.id, EstablecerAvanceMetaRequest(cantidad=3, anterior=0, motivo='Pantalla anterior'), self.db, self.users['teacher'])
        self.expect_status(403, establecer_avance, meta.id, payload, self.db, self.users['student'])
        self.assertEqual(self.db.query(Meta).count(), 1); self.assertEqual(self.db.query(Auditoria).count(), 2)

    def test_hours_goals_use_validated_records_and_cannot_be_set_manually(self):
        meta = self.goal('HORAS')
        for state, hours in [('VALIDADO', 2), ('PENDIENTE', 8), ('RECHAZADO', 5)]:
            self.db.add(RegistroHoras(practica_id='p', horas=hours, descripcion='Actividad', estado_validacion=RegistroHorasEstadoEnum(state)))
        self.db.commit()
        self.assertEqual(list_by_practica('p', self.db, self.users['student'])[0].cantidadAlcanzada, 2)
        self.expect_status(409, establecer_avance, meta.id, EstablecerAvanceMetaRequest(cantidad=9, anterior=2, motivo='Manual'), self.db, self.users['teacher'])

    def test_closed_practice_and_legacy_increment_are_blocked(self):
        meta = self.goal()
        self.expect_status(409, registrar_avance, meta.id, RegistrarAvanceMetaRequest(cantidad=2), self.db, self.users['teacher'])
        self.db.get(Practica, 'p').estado = PracticaEstadoEnum.CERRADA; self.db.commit()
        self.expect_status(409, self.goal, 'ARTICULOS', 'goal-00000000000002')
        self.expect_status(409, establecer_avance, meta.id, EstablecerAvanceMetaRequest(cantidad=1, anterior=0, motivo='Revisión'), self.db, self.users['teacher'])
        self.assertEqual(self.db.query(Auditoria).count(), 1)

    def test_content_and_quantities_are_validated(self):
        for cls, payload in [(CreateAnuncioRequest, {'titulo': ' ', 'mensaje': 'Texto'}), (CreateHiloRequest, {'titulo': 'x'*201}), (CreateForoMensajeRequest, {'texto': ' '}), (CreateMetaRequest, {'tipo': 'ARTICULOS', 'cantidadObjetivo': True}), (EstablecerAvanceMetaRequest, {'cantidad': 2, 'anterior': 0, 'motivo': ' '})]:
            with self.assertRaises(ValidationError): cls(**payload)


if __name__ == '__main__': unittest.main()
