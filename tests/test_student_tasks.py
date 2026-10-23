"""Páginas y detalle de tareas; SQLite en memoria, sin escrituras en Supabase."""
import unittest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, AulaEstadoEnum, Inscripcion, Tarea, Entrega, EntregaEstadoEnum, Empresa, Practica, PracticaEstadoEnum
from app.routers.alumno_tasks import task_page, task_detail


class StudentTasksTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,autoflush=False)()
        self.users={}
        for name,role in [('student','ALUMNO'),('other','ALUMNO'),('teacher','PROFESOR')]:
            user=User(id=name,nombres=name,apellidos='Test',email=name+'@example.org',hashed_password='unused',role=RoleEnum(role))
            self.users[name]=user;self.db.add(user)
        self.db.add(Aula(id='a',nombre='Aula',codigo='PAGE',periodo='TEST',profesor_id='teacher'))
        self.db.add(Inscripcion(id='i',aula_id='a',alumno_id='student'))
        for i in range(45):
            task_id=f't-{i:03}'
            self.db.add(Tarea(id=task_id,aula_id='a',titulo='Tarea '+str(i),descripcion='Instrucciones extensas',fecha_limite=datetime.now(timezone.utc)+timedelta(days=3) if i<30 else None))
            if i<10:
                self.db.add(Entrega(id='e-'+str(i),tarea_id=task_id,alumno_id='student',descripcion='Respuesta privada',estado=EntregaEstadoEnum.CALIFICADA if i<5 else EntregaEstadoEnum.ENTREGADA,nota=i if i<5 else None))
        self.db.add(Entrega(id='foreign-delivery',tarea_id='t-020',alumno_id='other',descripcion='De otra cuenta',nota=20))
        self.db.commit()
        # Empate real de fecha para comprobar que el ID desempata de forma estable.
        due=datetime.now(timezone.utc)+timedelta(days=3)
        self.db.query(Tarea).filter(Tarea.fecha_limite.is_not(None)).update({Tarea.fecha_limite:due})
        self.db.commit()

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def page(self,filter='todas',cursor=None):
        return task_page('a',filter,20,cursor,self.db,self.users['student'])

    def expect(self,status,fn,*args):
        with self.assertRaises(HTTPException) as result:fn(*args)
        self.assertEqual(result.exception.status_code,status)

    def test_stable_pages_include_null_deadlines_without_private_delivery_text(self):
        first=self.page();second=self.page(cursor=first['siguiente']);last=self.page(cursor=second['siguiente'])
        self.assertEqual([len(p['items']) for p in [first,second,last]],[20,20,5])
        ids=[item['id'] for p in [first,second,last] for item in p['items']]
        self.assertEqual(ids,sorted(set(ids)));self.assertIsNone(last['siguiente'])
        self.assertEqual(last['resumen'],first['resumen'])
        self.assertNotIn('descripcion',first['items'][0]);self.assertNotIn('entrega',first['items'][0])

    def test_server_filters_global_counts_and_zero_grade(self):
        pending=self.page('pendientes');graded=self.page('calificadas')
        self.assertEqual(pending['total'],35);self.assertEqual(len(pending['items']),20)
        self.assertEqual(pending['resumen'],{'total':45,'pendientes':35,'entregadas':10,'calificadas':5,'promedio':2.0})
        self.assertEqual(graded['items'][0]['nota'],0)
        self.assertEqual(self.page('entregadas')['total'],10)
        self.assertTrue(all(item['estado']=='PENDIENTE' for item in pending['items']))
        self.assertTrue(any(item['id']=='t-020' for item in pending['items']))

    def test_detail_has_only_own_delivery_and_reports_graded_state(self):
        graded=task_detail('a','t-000',self.db,self.users['student'])
        self.assertEqual(graded.entrega.nota,0);self.assertFalse(graded.entregaHabilitada)
        self.assertNotIn('cambios',self.db.get(Tarea,'t-000').__dict__)
        self.assertNotIn('versiones',self.db.get(Entrega,'e-0').__dict__)
        own=task_detail('a','t-020',self.db,self.users['student'])
        self.assertIsNone(own.entrega);self.assertTrue(own.entregaHabilitada)
        self.assertEqual(own.aulaNombre,'Aula')

    def test_permissions_missing_task_and_removed_enrollment(self):
        for name in ['other','teacher']:
            self.expect(403,task_detail,'a','t-000',self.db,self.users[name])
            self.expect(403,task_page,'a','todas',20,None,self.db,self.users[name])
        self.expect(404,task_detail,'a','missing',self.db,self.users['student'])
        self.db.delete(self.db.get(Inscripcion,'i'));self.db.commit()
        self.expect(403,task_detail,'a','t-020',self.db,self.users['student'])

    def test_deadline_class_and_practice_closure_block_delivery(self):
        task=self.db.get(Tarea,'t-020');task.fecha_limite=datetime.now(timezone.utc)-timedelta(days=1);self.db.commit()
        self.assertIn('plazo',task_detail('a',task.id,self.db,self.users['student']).bloqueoEntrega)
        task.fecha_limite=None;self.db.get(Aula,'a').estado=AulaEstadoEnum.CONCLUIDA;self.db.commit()
        self.assertIn('aula',task_detail('a',task.id,self.db,self.users['student']).bloqueoEntrega)
        self.db.get(Aula,'a').estado=AulaEstadoEnum.ACTIVA
        self.db.add(Empresa(id='company',practicante_id='student',razon_social='Centro',ruc='00000000001',direccion='Test'))
        self.db.add(Practica(id='p',practicante_id='student',aula_id='a',empresa_id='company',periodo='TEST',estado=PracticaEstadoEnum.CERRADA))
        self.db.commit()
        self.assertIn('práctica',task_detail('a',task.id,self.db,self.users['student']).bloqueoEntrega)

    def test_invalid_cursor_is_rejected(self):
        for cursor in ['broken','invalid-date|id','2026-10-23T12:00:00+00:00|']:
            self.expect(422,self.page,'todas',cursor)


if __name__=='__main__':unittest.main()
