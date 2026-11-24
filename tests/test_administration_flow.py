"""Gestión académica y seguridad; SQLite aislado, sin datos reales."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, AulaEstadoEnum, Entrega, Inscripcion, Auditoria, Practica, RegistroAsistencia, RegistroHoras, RegistroHorasEstadoEnum, Tarea
from app.routers.admin import crear_aula_admin, update_rol, cambiar_estado_aula, asignar_profesor, get_matriculas, establecer_matricula, reportes, usuarios_pagina, aulas_pagina, matriculas_pagina, detalle_aula_admin, reportes_pagina, auditoria_pagina
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

    def test_paged_admin_reads_with_global_totals_and_scopes(self):
        fecha = datetime(2026, 10, 24, tzinfo=timezone.utc)
        for i in range(24):
            self.db.add(Aula(id=f'pa-{i:02}', nombre=f'Aula paginada {i:02}', codigo=f'PA-{i:02}', periodo='TEST',
                profesor_id='teacher', estado=AulaEstadoEnum.CONCLUIDA if i % 3 == 0 else AulaEstadoEnum.ACTIVA))
            self.db.add(User(id=f'pu-{i:02}', nombres=f'Paginado {i:02}', apellidos='Estudiante',
                email=f'pu{i:02}@unsa.edu.pe', hashed_password='unused', role=RoleEnum.ALUMNO))
            self.db.add(Auditoria(id=f'au-{i:02}', user_id='admin', user_nombre='Admin Prueba', accion='ESTADO_AULA',
                detalle=f'Cambio {i:02}', fecha=fecha - timedelta(days=i)))
        self.db.add(Auditoria(id='au-att', user_id='admin', user_nombre='Admin Prueba', accion='ASISTENCIA_ACADEMICA',
            detalle=json.dumps({'aulaId': 'a', 'fecha': '2026-10-20', 'antes': [{'id': 'x1', 'practicanteId': 'student', 'presente': True}],
                'despues': [{'practicanteId': 'student', 'presente': False}]}), fecha=fecha))
        self.db.add(Auditoria(id='au-horas', user_id='admin', user_nombre='Admin Prueba', accion='HORAS_VALIDACION',
            detalle='Validacion de actividad h-1: 2 h; VALIDADO.', fecha=fecha))
        self.db.add(Tarea(id='tp', aula_id='a', titulo='Informe', descripcion=''))
        self.db.add(Entrega(id='ent1', tarea_id='tp', alumno_id='student', nota=16))
        self.db.add(Entrega(id='ent2', tarea_id='tp', alumno_id='student2', nota=20))
        self.db.add(RegistroAsistencia(id='as1', practicante_id='student', aula_id='a', fecha=fecha, presente=1))
        self.db.add(RegistroAsistencia(id='as2', practicante_id='student2', aula_id='a', fecha=fecha, presente=0))
        self.db.add(RegistroHoras(id='hr', practica_id='p', horas=8, descripcion='Prueba', estado_validacion=RegistroHorasEstadoEnum.VALIDADO))
        self.db.commit()
        admin = self.users['admin']

        users = usuarios_pagina('TODOS', '', 20, None, self.db, admin)
        self.assertEqual((users['total'], len(users['items']), users['totalDocentes']), (31, 20, 2))
        self.assertNotEqual(users['siguiente'], None)
        tail = usuarios_pagina('TODOS', '', 20, users['siguiente'], self.db, admin)
        self.assertEqual((tail['total'], len(tail['items']), tail['siguiente']), (31, 11, None))
        self.assertEqual(len({row['id'] for row in users['items'] + tail['items']}), 31)
        self.assertEqual(usuarios_pagina('ALUMNO', '', 20, None, self.db, admin)['total'], 27)
        profesores = usuarios_pagina('PROFESOR', '', 20, None, self.db, admin)
        self.assertEqual((profesores['total'], profesores['totalDocentes']), (2, 2))
        self.assertEqual(usuarios_pagina('TODOS', 'Paginado 03', 20, None, self.db, admin)['total'], 1)
        self.expect(422, usuarios_pagina, 'PROFESOR', '', 20, users['siguiente'], self.db, admin)
        self.expect(422, usuarios_pagina, 'INVALID', '', 20, None, self.db, admin)
        self.expect(422, usuarios_pagina, 'TODOS', '', 0, None, self.db, admin)
        self.expect(403, usuarios_pagina, 'TODOS', '', 20, None, self.db, self.users['student'])

        aulas = aulas_pagina('TODAS', '', 20, None, self.db, admin)
        self.assertEqual((aulas['total'], len(aulas['items']), aulas['aulasActivas']), (25, 20, 17))
        self.assertEqual(aulas['items'][0]['nombre'], 'Aula')
        rest = aulas_pagina('TODAS', '', 20, aulas['siguiente'], self.db, admin)
        self.assertEqual((rest['total'], len(rest['items']), rest['siguiente']), (25, 5, None))
        concluidas = aulas_pagina('CONCLUIDA', '', 20, None, self.db, admin)
        self.assertEqual((concluidas['total'], concluidas['aulasActivas']), (8, 17))
        self.assertEqual(aulas_pagina('ACTIVA', '', 20, None, self.db, admin)['total'], 17)
        self.assertEqual(aulas_pagina('TODAS', 'PA-13', 20, None, self.db, admin)['total'], 1)
        self.expect(422, aulas_pagina, 'ACTIVA', '', 20, aulas['siguiente'], self.db, admin)
        self.expect(422, aulas_pagina, 'INVALID', '', 20, None, self.db, admin)
        self.expect(403, aulas_pagina, 'TODAS', '', 20, None, self.db, self.users['supervisor'])

        detail = detalle_aula_admin('a', self.db, admin)
        self.assertEqual((detail['id'], detail['inscritos'], detail['descripcion'], detail['estado']), ('a', 1, '', 'ACTIVA'))
        self.expect(404, detalle_aula_admin, 'missing', self.db, admin)

        roster = matriculas_pagina('a', 'TODOS', '', 20, None, self.db, admin)
        self.assertEqual((roster['revision'], roster['matriculados'], roster['total']), (get_matriculas('a', self.db, admin).revision, 1, 27))
        matriculados = matriculas_pagina('a', 'MATRICULADOS', '', 20, None, self.db, admin)
        self.assertEqual((matriculados['total'], matriculados['items'][0]['alumnoId'], matriculados['items'][0]['inscrito']), (1, 'student', True))
        self.assertEqual(matriculas_pagina('a', 'SIN_MATRICULA', '', 20, None, self.db, admin)['total'], 26)
        self.assertEqual(matriculas_pagina('a', 'TODOS', 'student2', 20, None, self.db, admin)['total'], 1)
        self.expect(422, matriculas_pagina, 'a', 'INVALID', '', 20, None, self.db, admin)
        self.expect(404, matriculas_pagina, 'missing', 'TODOS', '', 20, None, self.db, admin)
        self.expect(403, matriculas_pagina, 'a', 'TODOS', '', 20, None, self.db, self.users['teacher'])

        report = reportes_pagina('TODAS', '', 20, None, self.db, admin)
        self.assertEqual(report['resumen'], {'totalAlumnos': 27, 'totalProfesores': 2, 'totalAulas': 25, 'aulasActivas': 17,
            'practicasEnCurso': 1, 'practicasCerradas': 0, 'horasPromedio': 8.0})
        first = next(row for row in report['items'] if row['id'] == 'a')
        self.assertEqual((first['inscritos'], first['promedioNotas'], first['asistenciaPct']), (1, 18.0, 50))
        filtrado = reportes_pagina('CONCLUIDA', '', 20, None, self.db, admin)
        self.assertEqual((filtrado['total'], filtrado['resumen']), (8, report['resumen']))
        self.expect(422, reportes_pagina, 'ACTIVA', '', 20, report['siguiente'], self.db, admin)
        self.expect(403, reportes_pagina, 'TODAS', '', 20, None, self.db, self.users['student'])

        audit = auditoria_pagina('TODAS', '', 20, None, self.db, admin)
        self.assertEqual((audit['total'], len(audit['items'])), (26, 20))
        rest = auditoria_pagina('TODAS', '', 20, audit['siguiente'], self.db, admin)
        self.assertEqual((rest['total'], len(rest['items']), rest['siguiente']), (26, 6, None))
        attendance = auditoria_pagina('ASISTENCIA', '', 20, None, self.db, admin)['items'][0]
        self.assertEqual((attendance['aulaNombre'], attendance['estudiantes']), ('Aula', [{'id': 'student', 'nombre': 'student Prueba'}]))
        self.assertEqual(auditoria_pagina('HORAS', '', 20, None, self.db, admin)['total'], 1)
        self.assertEqual(auditoria_pagina('ADMIN', '', 20, None, self.db, admin)['total'], 24)
        self.assertEqual(auditoria_pagina('TODAS', 'Cambio 05', 20, None, self.db, admin)['total'], 1)
        self.expect(422, auditoria_pagina, 'ASISTENCIA', '', 20, audit['siguiente'], self.db, admin)
        self.expect(422, auditoria_pagina, 'INVALID', '', 20, None, self.db, admin)
        self.expect(403, auditoria_pagina, 'TODAS', '', 20, None, self.db, self.users['student'])

if __name__=='__main__':unittest.main()
