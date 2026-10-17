import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User,RoleEnum,Aula,AulaEstadoEnum,Inscripcion,MensajeDirecto,Auditoria
from app.routers.comunicacion import enviar_mensaje,conversacion,list_contactos,marcar_lectura
from app.schemas.schemas import EnviarMensajeRequest,LeerMensajesRequest

class DirectMessagesTests(unittest.TestCase):
 def setUp(self):
  self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine);self.db=sessionmaker(bind=self.engine,autoflush=False)();self.users={}
  for name,role in [('teacher','PROFESOR'),('otherteacher','PROFESOR'),('student','ALUMNO'),('peer','ALUMNO'),('outsider','ALUMNO'),('admin','ADMIN')]:
   user=User(id=name,nombres=name,apellidos='Prueba',email=f'{name}@unsa.edu.pe',hashed_password='unused',role=RoleEnum(role));self.db.add(user);self.users[name]=user
  self.db.add(Aula(id='a',nombre='Aula',codigo='A1',periodo='TEST',profesor_id='teacher'))
  for name in ['student','peer']:self.db.add(Inscripcion(alumno_id=name,aula_id='a'))
  self.db.commit()
 def tearDown(self):self.db.close();self.engine.dispose()
 def expect(self,code,fn,*args):
  with self.assertRaises(HTTPException) as r:fn(*args)
  self.assertEqual(r.exception.status_code,code);self.db.rollback()
 def send(self,text='Consulta de práctica',key='message-00000000001'):
  return enviar_mensaje('a','teacher',EnviarMensajeRequest(texto=text,solicitudId=key),self.db,self.users['student'])
 def test_send_retry_and_changed_payload(self):
  one=self.send();self.assertEqual(self.send().id,one.id);self.expect(409,self.send,'Otro texto');self.assertEqual(self.db.query(MensajeDirecto).count(),1);self.assertEqual(self.db.query(Auditoria).count(),1)
  self.assertNotIn('Consulta de práctica',self.db.query(Auditoria).one().detalle)
 def test_current_teacher_student_pair_only(self):
  payload=EnviarMensajeRequest(texto='Consulta')
  for target in ['peer','outsider','otherteacher','admin','student']:self.expect(403,enviar_mensaje,'a',target,payload,self.db,self.users['student'])
  self.expect(403,enviar_mensaje,'a','student',payload,self.db,self.users['otherteacher'])
  self.expect(403,list_contactos,'a',self.db,self.users['admin'])
 def test_get_does_not_mark_as_read_and_explicit_receipt_is_idempotent(self):
  one=self.send();view=conversacion('a','student',self.db,self.users['teacher']);self.assertFalse(view[0].leido);self.assertFalse(view[0].mio)
  self.assertEqual(next(c for c in list_contactos('a',self.db,self.users['teacher']) if c.userId=='student').noLeidos,1)
  for _ in range(2):self.assertEqual(marcar_lectura('a','student',LeerMensajesRequest(mensajeIds=[one.id]),self.db,self.users['teacher'])['mensajeIds'],[one.id])
  self.assertTrue(conversacion('a','teacher',self.db,self.users['student'])[0].leido);self.assertEqual(list_contactos('a',self.db,self.users['teacher'])[0].noLeidos,0)
  self.assertEqual(self.db.query(Auditoria).count(),1)
 def test_cannot_read_or_mark_another_students_message(self):
  one=self.send();self.assertEqual(conversacion('a','teacher',self.db,self.users['peer']),[])
  self.expect(404,marcar_lectura,'a','teacher',LeerMensajesRequest(mensajeIds=[one.id]),self.db,self.users['peer'])
  self.expect(404,marcar_lectura,'a','teacher',LeerMensajesRequest(mensajeIds=[one.id]),self.db,self.users['student'])
  self.assertEqual(self.db.query(MensajeDirecto).one().leido,0)
 def test_closed_class_allows_read_receipt_but_not_new_messages(self):
  one=self.send();self.db.get(Aula,'a').estado=AulaEstadoEnum.CONCLUIDA;self.db.commit()
  self.expect(409,self.send,'Otra consulta','message-00000000002');self.assertEqual(len(conversacion('a','teacher',self.db,self.users['student'])),1)
  marcar_lectura('a','student',LeerMensajesRequest(mensajeIds=[one.id]),self.db,self.users['teacher'])
 def test_withdrawal_revokes_access_without_deleting_messages(self):
  self.send();self.db.delete(self.db.query(Inscripcion).filter(Inscripcion.alumno_id=='student').one());self.db.commit()
  self.expect(403,conversacion,'a','teacher',self.db,self.users['student']);self.expect(403,conversacion,'a','student',self.db,self.users['teacher']);self.assertEqual(self.db.query(MensajeDirecto).count(),1)
 def test_content_validation(self):
  for text in [' ','x'*10001]:
   with self.assertRaises(ValidationError):EnviarMensajeRequest(texto=text)
  with self.assertRaises(ValidationError):LeerMensajesRequest(mensajeIds=['same','same'])

if __name__=='__main__':unittest.main()
