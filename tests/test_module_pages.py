"""Páginas, ámbitos y metadatos; sin escrituras en Supabase."""
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from app.models.models import Anuncio, Aula, AulaEstadoEnum, ContenidoArchivo, Archivo, ForoHilo, ForoMensaje, Inscripcion, MensajeDirecto, User
from app.routers import module_pages as pages
import test_direct_messages as fixture


class ModulePagesTests(unittest.TestCase):
    setUp = fixture.DirectMessagesTests.setUp
    tearDown = fixture.DirectMessagesTests.tearDown
    expect = fixture.DirectMessagesTests.expect

    def rows(self):
        date = datetime(2026, 10, 23, tzinfo=timezone.utc)
        for i in range(45):
            key = f'{i:03}'
            self.db.add(Anuncio(id='an-' + key, aula_id='a', autor_id='teacher', autor_nombre='Docente', titulo='Anuncio ' + key, mensaje='Contenido ' * 1000, fijado=int(i < 17), created_at=date))
            self.db.add(ForoHilo(id='fh-' + key, aula_id='a', autor_id='student', autor_nombre='Alumno', titulo='Tema ' + key, created_at=date))
            self.db.add(ForoMensaje(id='fm-' + key, hilo_id='fh-000', autor_id='student', autor_nombre='Alumno', texto='Respuesta ' + key, created_at=date))
            self.db.add(MensajeDirecto(id='md-' + key, aula_id='a', remitente_id='teacher', destinatario_id='student', texto='Mensaje ' + key, created_at=date, leido=0))
        self.db.commit()

    def all_pages(self, fn):
        first = fn(None); second = fn(first['siguiente']); last = fn(second['siguiente'])
        self.assertEqual([len(page['items']) for page in [first, second, last]], [20, 20, 5])
        self.assertEqual([page['total'] for page in [first, second, last]], [45, 45, 45])
        self.assertIsNone(last['siguiente'])
        rows = [row for page in [first, second, last] for row in page['items']]
        self.assertEqual(len({row['id'] if isinstance(row, dict) else row.id for row in rows}), 45)
        return rows

    def test_announcement_pin_order_summary_and_detail(self):
        self.rows()
        rows = self.all_pages(lambda cursor: pages.announcements('a', False, 20, cursor, self.db, self.users['student']))
        self.assertEqual([row['id'] for row in rows], [f'an-{i:03}' for i in list(range(16, -1, -1)) + list(range(44, 16, -1))])
        self.assertTrue(all(len(row['resumen']) == 180 and 'mensaje' not in row for row in rows))
        only = pages.announcements('a', True, 20, None, self.db, self.users['student'])
        self.assertEqual(only['total'], 17); self.assertIsNone(only['siguiente'])
        self.assertEqual(len(pages.announcement('a', 'an-000', self.db, self.users['student']).mensaje), 10000)

    def test_threads_and_replies_stable_pages_and_exact_context(self):
        self.rows()
        rows = self.all_pages(lambda cursor: pages.threads('a', 20, cursor, self.db, self.users['student']))
        self.assertEqual(rows[-1]['respuestas'], 45)
        replies = self.all_pages(lambda cursor: pages.forum_messages('fh-000', 20, cursor, self.db, self.users['student']))
        self.assertEqual(replies[0].id, 'fm-044')
        self.assertEqual(pages.thread('a', 'fh-000', self.db, self.users['student'])['respuestas'], 45)
        self.db.add(Aula(id='b', nombre='Otra aula', codigo='B', periodo='TEST', profesor_id='teacher'))
        self.db.add(Inscripcion(aula_id='b', alumno_id='student')); self.db.commit()
        self.expect(404, pages.thread, 'b', 'fh-000', self.db, self.users['student'])
        self.expect(404, pages.announcement, 'b', 'an-000', self.db, self.users['student'])

    def test_direct_unread_is_global_and_other_students_are_excluded(self):
        self.rows()
        self.db.add(MensajeDirecto(id='foreign', aula_id='a', remitente_id='teacher', destinatario_id='peer', texto='Privado ajeno'))
        self.db.commit()
        rows = self.all_pages(lambda cursor: pages.direct_messages('a', 'teacher', 20, cursor, self.db, self.users['student']))
        self.assertTrue(all(row.destinatarioId == 'student' and not row.leido for row in rows))
        self.assertEqual(pages.direct_messages('a', 'teacher', 20, None, self.db, self.users['student'])['noLeidos'], 45)
        self.assertEqual(self.db.query(MensajeDirecto).filter(MensajeDirecto.leido == 0).count(), 46)
        self.expect(403, pages.direct_messages, 'a', 'peer', 20, None, self.db, self.users['student'])
        self.expect(403, pages.direct_messages, 'a', 'teacher', 20, None, self.db, self.users['admin'])

    def test_cursor_rejected_between_queries_and_invalid_values(self):
        self.rows()
        first = pages.announcements('a', False, 20, None, self.db, self.users['student'])
        self.expect(422, pages.announcements, 'a', True, 20, first['siguiente'], self.db, self.users['student'])
        self.expect(422, pages.threads, 'a', 20, first['siguiente'], self.db, self.users['student'])
        for value in ['bad', 'x' * 2050]:
            self.expect(422, pages.threads, 'a', 20, value, self.db, self.users['student'])
        self.expect(422, pages.threads, 'a', 0, None, self.db, self.users['student'])

    def test_membership_withdrawn_and_closed_class_reads(self):
        self.rows()
        self.db.get(Aula, 'a').estado = AulaEstadoEnum.CONCLUIDA; self.db.commit()
        self.assertEqual(pages.forum_messages('fh-000', 20, None, self.db, self.users['student'])['total'], 45)
        self.db.delete(self.db.query(Inscripcion).filter(Inscripcion.alumno_id == 'student').one()); self.db.commit()
        self.expect(403, pages.forum_messages, 'fh-000', 20, None, self.db, self.users['student'])
        self.expect(403, pages.threads, 'a', 20, None, self.db, self.users['student'])
        self.expect(403, pages.direct_messages, 'a', 'student', 20, None, self.db, self.users['teacher'])

    def test_file_filters_exclude_private_files_and_do_not_load_bytes(self):
        for key, user, material in [('own', 'student', 0), ('private', 'peer', 0), ('material', 'teacher', 1)]:
            self.db.add(Archivo(id=key, aula_id='a', subido_por_id=user, nombre_original=key + '.pdf', nombre_guardado=key, tipo_mime='application/pdf', tamanio=50000))
            self.db.add(ContenidoArchivo(archivo_id=key, datos=b'x' * 50000, sha256='a' * 64, material=material))
        self.db.commit(); self.db.expunge_all()
        self.users = {key: self.db.get(User, key) for key in self.users}
        rows = pages.files('a', 'todos', 20, None, self.db, self.users['student'])
        self.assertEqual({row.id for row in rows['items']}, {'own', 'material'})
        self.assertFalse(any(isinstance(row, ContenidoArchivo) for row in self.db.identity_map.values()))
        self.assertEqual([row.id for row in pages.files('a', 'materiales', 20, None, self.db, self.users['student'])['items']], ['material'])
        self.assertEqual([row.id for row in pages.files('a', 'propios', 20, None, self.db, self.users['student'])['items']], ['own'])
        self.expect(422, pages.files, 'a', 'invalid', 20, None, self.db, self.users['student'])


if __name__ == '__main__':
    unittest.main()
