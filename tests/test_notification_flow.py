"""Avisos paginados, destinos y eventos; SQLite aislado, sin Supabase."""
import unittest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, Inscripcion, Empresa, Practica, Supervisor, RegistroHoras, Notificacion, NotificacionTipoEnum
from app.routers.notificaciones import bandeja, get_notificacion, mark_read, mark_all_read
from app.routers.tareas import create_tarea, editar_tarea, EditarTareaRequest
from app.routers.empresa import revisar_horas
from app.schemas.schemas import CreateTareaRequest, RevisarHorasRequest


class NotificationFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name,role in [('student','ALUMNO'),('other','ALUMNO'),('teacher','PROFESOR'),('supervisor','SUPERVISOR')]:
            u=User(id=name,nombres=name,apellidos='Test',email=name+'@example.org',hashed_password='unused',role=RoleEnum(role))
            self.users[name]=u; self.db.add(u)
        self.db.add(Aula(id='a',nombre='Aula',codigo='NOTICE',periodo='TEST',profesor_id='teacher'))
        self.db.add(Inscripcion(id='i',aula_id='a',alumno_id='student'))
        self.db.add(Empresa(id='e',practicante_id='student',razon_social='Centro',ruc='00000000001',direccion='Test'))
        self.db.add(Practica(id='p',aula_id='a',practicante_id='student',empresa_id='e',periodo='TEST',horas_minimas=200))
        self.db.add(Supervisor(id='s',empresa_id='e',user_id='supervisor',nombres='Test',apellidos='Test'))
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def notices(self):
        for i in range(45):
            self.db.add(Notificacion(id=f'n-{i:03}',user_id='student',tipo=NotificacionTipoEnum.TAREA_ASIGNADA,titulo='Aviso',mensaje='Test',leida=0 if i<30 else 1,fecha=datetime(2026,10,20,tzinfo=timezone.utc)))
        self.db.add(Notificacion(id='foreign',user_id='other',tipo=NotificacionTipoEnum.VENCIMIENTO,titulo='Otro',leida=0))
        self.db.commit()

    def page(self,filter='todos',cursor=None):
        return bandeja(filter,20,cursor,self.db,self.users['student'])

    def expect(self,status,fn,*args):
        with self.assertRaises(HTTPException) as result: fn(*args)
        self.assertEqual(result.exception.status_code,status)

    def test_keyset_pages_counts_and_explicit_read(self):
        self.notices()
        first=self.page();second=self.page(cursor=first.siguiente);last=self.page(cursor=second.siguiente)
        self.assertEqual([len(p.items) for p in [first,second,last]],[20,20,5])
        ids=[n.id for p in [first,second,last] for n in p.items]
        self.assertEqual(ids,sorted(set(ids),reverse=True))
        self.assertIsNone(last.siguiente)
        self.assertEqual(last.sinLeer,30);self.assertEqual(last.total,45)
        self.assertFalse(get_notificacion('n-000',self.db,self.users['student']).leida)
        self.assertEqual(self.page('pendientes').total,30)
        self.assertEqual(self.page('leidos').sinLeer,30)

    def test_owned_read_and_invalid_cursor(self):
        self.notices()
        for fn in [get_notificacion,mark_read]:
            self.expect(404,fn,'foreign',self.db,self.users['student'])
        self.expect(422,self.page,'todos','bad-cursor')
        mark_read('n-000',self.db,self.users['student'])
        mark_read('n-000',self.db,self.users['student'])
        self.assertEqual(self.page().sinLeer,29)
        mark_all_read(self.db,self.users['student'])
        self.assertEqual(self.page().sinLeer,0)
        self.assertEqual(self.db.get(Notificacion,'foreign').leida,0)

    def test_legacy_and_invalid_destinations_remain_informative(self):
        self.notices()
        notice=self.db.get(Notificacion,'n-000')
        self.assertIsNone(get_notificacion(notice.id,self.db,self.users['student']).destino)
        for value in [{'tipo':[]},{'tipo':'URL','url':'https://example.org'},{'tipo':'TAREA','aulaId':'a'},{'tipo':'TAREA','aulaId':'a','tareaId':'t','url':'x'}]:
            notice.destino=value;self.db.commit()
            self.assertIsNone(get_notificacion(notice.id,self.db,self.users['student']).destino)

    def test_task_events_are_atomic_scoped_and_idempotent(self):
        body=CreateTareaRequest(titulo='Entrevista',descripcion='Instrucciones',fechaLimite=datetime.now(timezone.utc)+timedelta(days=2),solicitudId='notice-task-00000001')
        task=create_tarea('a',body,self.db,self.users['teacher'])
        create_tarea('a',body,self.db,self.users['teacher'])
        self.assertEqual(self.db.query(Notificacion).count(),1)
        n=self.page().items[0]
        self.assertEqual(n.destino.model_dump(),{'tipo':'TAREA','aulaId':'a','tareaId':task.id})
        changed=EditarTareaRequest(**{**body.model_dump(),'titulo':'Entrevista ampliada','revision':0,'motivo':'Instrucciones aclaradas'})
        editar_tarea('a',task.id,changed,self.db,self.users['teacher'])
        editar_tarea('a',task.id,changed,self.db,self.users['teacher'])
        self.assertEqual(self.db.query(Notificacion).count(),2)
        self.assertEqual({n.tipo for n in self.page().items},{'TAREA_ASIGNADA','TAREA_ACTUALIZADA'})
        self.assertEqual(bandeja('todos',20,None,self.db,self.users['other']).total,0)

    def test_hours_review_notifies_owner_once(self):
        self.db.add(RegistroHoras(id='r',practica_id='p',fecha=datetime.now(timezone.utc),horas=2,descripcion='Actividad de prueba'))
        self.db.commit()
        body=RevisarHorasRequest(estadoValidacion='RECHAZADO',revision=0,observacion='Detalla la actividad')
        revisar_horas('r',body,self.db,self.users['supervisor'])
        revisar_horas('r',body,self.db,self.users['supervisor'])
        page=self.page()
        self.assertEqual(page.total,1)
        self.assertEqual(page.items[0].tipo,'REVISION_HORAS')
        self.assertEqual(page.items[0].destino.model_dump(),{'tipo':'ACTIVIDAD','practicaId':'p','registroId':'r'})
        self.assertFalse(page.items[0].leida)

    def test_transaction_rollback_does_not_leave_an_orphan_notice(self):
        from app.core.notices import add_notice
        add_notice(self.db,'student','uncommitted','TAREA_ASIGNADA','Aviso','Texto',{'tipo':'TAREA','aulaId':'a','tareaId':'missing'})
        self.db.flush();self.db.rollback()
        self.assertEqual(self.db.query(Notificacion).count(),0)


if __name__=='__main__': unittest.main()
