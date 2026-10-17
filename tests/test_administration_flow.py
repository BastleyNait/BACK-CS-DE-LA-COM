"""Gestión académica y seguridad; SQLite aislado, sin datos reales."""
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, AulaEstadoEnum, Inscripcion, Auditoria, Practica, RegistroHoras, RegistroHorasEstadoEnum
from app.routers.admin import crear_aula_admin, update_rol, cambiar_estado_aula, asignar_profesor, get_matriculas, establecer_matricula, reportes
from app.routers.aulas import create_aula
from app.routers.profesor import seguimiento_practicante
from app.routers.auth import register
from app.schemas.schemas import CreateAulaRequest, UpdateRolRequest, UpdateAulaEstadoRequest, AsignarProfesorRequest, EstablecerMatriculaRequest, RegisterRequest

class AdministrationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://'); Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine,autoflush=False)(); self.users={}
        for name,role in [('admin','ADMIN'),('teacher','PROFESOR'),('teacher2','PROFESOR'),('student','ALUMNO'),('student2','ALUMNO'),('unlinked','ALUMNO'),('supervisor','SUPERVISOR')]:
            u=User(id=name,nombres=name,apellidos='Prueba',email=f'{name}@unsa.edu.pe',hashed_password='unused',role=RoleEnum(role));self.db.add(u);self.users[name]=u
        self.db.add(Aula(id='a',nombre='Aula',codigo='A1',descripcion='',periodo='TEST',profesor_id='teacher',inscritos=99))
        self.db.add(Inscripcion(alumno_id='student',aula_id='a'));self.db.add(Practica(id='p',aula_id='a',practicante_id='student',periodo='TEST',horas_acumuladas=99));self.db.commit()
    def tearDown(self):self.db.close();self.engine.dispose()
    def expect(self,code,fn,*args):
        with self.assertRaises(HTTPException) as r:fn(*args)
        self.assertEqual(r.exception.status_code,code);self.db.rollback()
    def create(self,key='create-aula-00000001'):
        return crear_aula_admin(CreateAulaRequest(nombre='Nueva aula',codigo='new-1',descripcion='Seguimiento',periodo='2026-II',profesorId='teacher2',solicitudId=key),self.db,self.users['admin'])
    def test_class_creation_retry_unique_code_and_permissions(self):
        first=self.create();self.assertEqual(self.create().id,first.id);self.assertEqual(first.profesorId,'teacher2');self.assertEqual(first.codigo,'NEW-1')
        self.expect(409,self.create,'create-aula-00000002')
        self.expect(403,create_aula,CreateAulaRequest(nombre='Aula',codigo='XX',periodo='TEST'),self.db,self.users['supervisor'])
        self.expect(422,crear_aula_admin,CreateAulaRequest(nombre='Aula',codigo='XX',periodo='TEST'),self.db,self.users['admin'])
        self.assertEqual(self.db.query(Auditoria).count(),1)
    def test_role_change_stale_self_and_dependencies(self):
        p=UpdateRolRequest(role='PROFESOR',anterior='ALUMNO')
        self.expect(400,update_rol,'admin',UpdateRolRequest(role='ALUMNO',anterior='ADMIN'),self.db,self.users['admin'])
        self.expect(409,update_rol,'student',p,self.db,self.users['admin'])
        self.expect(409,update_rol,'teacher',UpdateRolRequest(role='ALUMNO',anterior='PROFESOR'),self.db,self.users['admin'])
        for _ in range(2):self.assertEqual(update_rol('unlinked',p,self.db,self.users['admin']).role,'PROFESOR')
        self.expect(409,update_rol,'unlinked',UpdateRolRequest(role='SUPERVISOR',anterior='ALUMNO'),self.db,self.users['admin'])
        self.expect(403,update_rol,'unlinked',p,self.db,self.users['teacher'])
        self.assertEqual(self.db.query(Auditoria).count(),1)
    def test_class_state_and_assignment_do_not_overwrite_or_duplicate_audit(self):
        p=UpdateAulaEstadoRequest(estado='CONCLUIDA',anterior='ACTIVA')
        for _ in range(2):self.assertEqual(cambiar_estado_aula('a',p,self.db,self.users['admin']).estado,'CONCLUIDA')
        self.expect(409,cambiar_estado_aula,'a',UpdateAulaEstadoRequest(estado='ACTIVA',anterior='ACTIVA'),self.db,self.users['admin'])
        assign=AsignarProfesorRequest(profesorId='teacher2',anterior='teacher')
        for _ in range(2):self.assertEqual(asignar_profesor('a',assign,self.db,self.users['admin']).profesorId,'teacher2')
        self.expect(409,asignar_profesor,'a',AsignarProfesorRequest(profesorId='teacher',anterior='teacher'),self.db,self.users['admin'])
        self.assertEqual(self.db.query(Auditoria).count(),2)
    def test_roster_revision_idempotence_count_and_withdraw_history(self):
        first=get_matriculas('a',self.db,self.users['admin']);payload=EstablecerMatriculaRequest(inscrito=True,revision=first.revision)
        for _ in range(2):self.assertTrue(next(x for x in establecer_matricula('a','student2',payload,self.db,self.users['admin']).alumnos if x.alumnoId=='student2').inscrito)
        self.assertEqual(self.db.get(Aula,'a').inscritos,2)
        self.expect(409,establecer_matricula,'a','unlinked',payload,self.db,self.users['admin'])
        fresh=get_matriculas('a',self.db,self.users['admin']);remove=EstablecerMatriculaRequest(inscrito=False,revision=fresh.revision)
        for _ in range(2):establecer_matricula('a','student',remove,self.db,self.users['admin'])
        self.assertEqual(self.db.query(Practica).count(),1);self.assertEqual(self.db.get(Aula,'a').inscritos,1);self.assertEqual(self.db.query(Auditoria).count(),2)
    def test_concluded_roster_and_non_student_are_protected(self):
        snap=get_matriculas('a',self.db,self.users['admin']);self.db.get(Aula,'a').estado=AulaEstadoEnum.CONCLUIDA;self.db.commit()
        p=EstablecerMatriculaRequest(inscrito=True,revision=snap.revision)
        self.expect(409,establecer_matricula,'a','student2',p,self.db,self.users['admin'])
        self.expect(404,establecer_matricula,'a','teacher',p,self.db,self.users['admin'])
        self.expect(403,get_matriculas,'a',self.db,self.users['student'])
    def test_public_registration_cannot_grant_privileged_roles(self):
        for role in ['ADMIN','PROFESOR','SUPERVISOR']:
            self.expect(403,register,RegisterRequest(nombres='Cuenta',apellidos='Prueba',email='nuevo@unsa.edu.pe',password='Prueba-local-123',role=role),self.db)
        self.assertEqual(self.db.query(User).count(),7)
    def test_report_and_followup_count_only_validated_hours(self):
        for state,hours in [('VALIDADO',2),('PENDIENTE',8),('RECHAZADO',4)]:self.db.add(RegistroHoras(practica_id='p',horas=hours,descripcion='Prueba',estado_validacion=RegistroHorasEstadoEnum(state)))
        self.db.commit();report=reportes(self.db,self.users['admin']);self.assertEqual(report.horasPromedio,2);self.assertEqual(report.aulas[0].inscritos,1)
        self.assertEqual(seguimiento_practicante('a','student',self.db,self.users['teacher']).horasAcumuladas,2)
        self.expect(404,seguimiento_practicante,'a','student2',self.db,self.users['teacher'])
        self.expect(403,seguimiento_practicante,'a','student',self.db,self.users['teacher2'])
    def test_strict_input(self):
        with self.assertRaises(ValidationError):EstablecerMatriculaRequest(inscrito=1,revision='a'*64)
        with self.assertRaises(ValidationError):CreateAulaRequest(nombre=' ',codigo='X1',periodo='TEST')

if __name__=='__main__':unittest.main()
