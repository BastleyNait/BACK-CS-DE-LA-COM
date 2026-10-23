"""Paginación y aislamiento de lecturas; solo SQLite en memoria."""
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base, get_db
from app.core.deps import get_current_user
from app.models.models import User, RoleEnum, Aula, Empresa, Practica, RegistroHoras, RegistroHorasEstadoEnum, Inscripcion, Tarea, Entrega
from app.routers.alumno_navigation import router, inicio, bitacora, actividad

class StudentNavigationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,autoflush=False)()
        self.users={}
        for name,role in [('student','ALUMNO'),('other','ALUMNO'),('teacher','PROFESOR')]:
            u=User(id=name,nombres=name,apellidos='Test',email=name+'@example.org',hashed_password='unused',role=RoleEnum(role))
            self.db.add(u);self.users[name]=u
        self.db.add(Aula(id='a1',nombre='Aula',codigo='NAV',periodo='TEST',profesor_id='teacher'))
        self.db.add(Empresa(id='e1',practicante_id='student',razon_social='Centro',ruc='00000000001',direccion='Test'))
        self.db.add(Practica(id='p1',practicante_id='student',aula_id='a1',empresa_id='e1',periodo='TEST',horas_minimas=200))
        self.db.add(Inscripcion(id='i1',aula_id='a1',alumno_id='student'))
        for i in range(45):
            self.db.add(RegistroHoras(id=f'h-{i:03}',practica_id='p1',fecha=datetime(2026,10,20,tzinfo=timezone.utc),horas=2,descripcion='Actividad de prueba',estado_validacion=RegistroHorasEstadoEnum.VALIDADO if i<30 else RegistroHorasEstadoEnum.PENDIENTE))
        self.db.commit()
    def tearDown(self):
        self.db.close();self.engine.dispose()
    def page(self,**kw):
        return bitacora('p1',limite=20,estado=None,cursor=None,db=self.db,current_user=self.users['student'],**kw)
    def test_stable_pages_and_global_totals(self):
        first=self.page()
        second=bitacora('p1',20,None,first['siguiente'],self.db,self.users['student'])
        last=bitacora('p1',20,None,second['siguiente'],self.db,self.users['student'])
        ids=[r.id for p in [first,second,last] for r in p['registros']]
        self.assertEqual([len(p['registros']) for p in [first,second,last]],[20,20,5])
        self.assertEqual(len(set(ids)),45);self.assertEqual(ids,sorted(ids,reverse=True))
        self.assertIsNone(last['siguiente'])
        self.assertEqual(first['resumen']['VALIDADO'],{'horas':60,'registros':30})
        self.assertEqual(last['resumen'],first['resumen'])
        self.assertNotIn('registros_horas',self.db.get(Practica,'p1').__dict__)
    def test_filter_and_counts_do_not_change_totals(self):
        page=bitacora('p1',8,'PENDIENTE',None,self.db,self.users['student'])
        self.assertEqual(page['coincidencias'],15)
        self.assertEqual(len(page['registros']),8)
        self.assertTrue(all(r.estadoValidacion=='PENDIENTE' for r in page['registros']))
        self.assertEqual(page['practica']['horasAcumuladas'],60)
        self.assertEqual(page['resumen']['PENDIENTE']['horas'],30)
    def test_permissions_and_invalid_cursor(self):
        for name,status in [('other',404),('teacher',403)]:
            with self.assertRaises(HTTPException) as result:
                bitacora('p1',20,None,None,self.db,self.users[name])
            self.assertEqual(result.exception.status_code,status)
        with self.assertRaises(HTTPException) as result:
            bitacora('p1',20,None,'invalid',self.db,self.users['student'])
        self.assertEqual(result.exception.status_code,422)
        with self.assertRaises(HTTPException) as result:
            actividad('p1','missing',self.db,self.users['student'])
        self.assertEqual(result.exception.status_code,404)
        self.assertEqual(actividad('p1','h-000',self.db,self.users['student'])['registro'].id,'h-000')
    def test_overview_membership_and_delivered_tasks(self):
        self.db.add(Tarea(id='t1',aula_id='a1',titulo='Ya entregada'))
        self.db.add(Tarea(id='t2',aula_id='a1',titulo='Pendiente'))
        self.db.add(Entrega(id='en1',tarea_id='t1',alumno_id='student'))
        self.db.commit()
        data=inicio(self.db,self.users['student'])
        self.assertEqual(data['proximaTarea']['id'],'t2')
        self.assertEqual(data['resumen']['VALIDADO']['horas'],60)
        empty=inicio(self.db,self.users['other'])
        self.assertEqual(empty['aulas'],[]);self.assertIsNone(empty['practica']);self.assertIsNone(empty['proximaTarea'])

if __name__=='__main__':unittest.main()
