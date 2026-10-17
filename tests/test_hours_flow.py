"""Regresión del circuito de horas; SQLite aislado, sin tocar Supabase."""
import unittest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, Empresa, Supervisor, Practica, RegistroHoras
from app.routers.practicas import registrar_horas, get_horas, cerrar_practica, historial, generar_reporte
from app.routers.empresa import revisar_horas
from app.schemas.schemas import RegistrarHorasRequest, RevisarHorasRequest


class HoursFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.users = {}
        for name, role in [("student", "ALUMNO"), ("other", "ALUMNO"), ("teacher", "PROFESOR"), ("otherteacher", "PROFESOR"), ("supervisor", "SUPERVISOR"), ("foreignsupervisor", "SUPERVISOR"), ("admin", "ADMIN")]:
            user = User(id=name, nombres=name, apellidos="Test", email=f"{name}@example.org", hashed_password="unused", role=RoleEnum(role))
            self.db.add(user)
            self.users[name] = user
        for suffix, student, teacher in [("1", "student", "teacher"), ("2", "other", "otherteacher")]:
            self.db.add(Aula(id="a"+suffix, nombre="Aula", codigo=suffix, periodo="TEST", profesor_id=teacher))
            self.db.add(Empresa(id="e"+suffix, practicante_id=student, razon_social="Centro", ruc="0000000000"+suffix, direccion="Test"))
            self.db.add(Practica(id="p"+suffix, practicante_id=student, aula_id="a"+suffix, empresa_id="e"+suffix, periodo="TEST", horas_minimas=2))
        self.db.add(Supervisor(id="s1", empresa_id="e1", user_id="supervisor", nombres="Test", apellidos="Test"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def submit(self, key="unit-000000000001", hours=2):
        return registrar_horas("p1", RegistrarHorasRequest(horas=hours, descripcion="Actividad de prueba", fecha=datetime.now(timezone(timedelta(hours=-5))).date().isoformat(), solicitudId=key), self.db, self.users["student"])

    def expect_status(self, status, fn, *args):
        with self.assertRaises(HTTPException) as raised:
            fn(*args)
        self.assertEqual(raised.exception.status_code, status)
        self.db.rollback()

    def test_pending_approval_repeat_and_closure(self):
        created = self.submit()
        self.assertEqual(created.practica.horasAcumuladas, 0)
        self.assertEqual(created.practica.estado, "EN_CURSO")
        self.expect_status(422, cerrar_practica, "p1", self.db, self.users["teacher"])
        payload = RevisarHorasRequest(estadoValidacion="VALIDADO")
        for _ in range(2):
            result = revisar_horas(created.registro.id, payload, self.db, self.users["supervisor"])
            self.assertEqual(result.estadoValidacion, "VALIDADO")
        self.assertEqual(self.db.get(Practica, "p1").horas_acumuladas, 2)
        self.assertEqual(cerrar_practica("p1", self.db, self.users["teacher"]).estado, "CERRADA")
        self.expect_status(409, self.submit, "unit-000000000002")

    def test_registration_is_idempotent_and_detects_changed_payload(self):
        first = self.submit()
        self.assertEqual(self.submit().registro.id, first.registro.id)
        self.assertEqual(self.db.query(RegistroHoras).count(), 1)
        self.expect_status(409, self.submit, "unit-000000000001", 3)

    def test_rejected_hours_do_not_count_or_allow_opposite_decision(self):
        created = self.submit()
        payload = RevisarHorasRequest(estadoValidacion="RECHAZADO")
        for _ in range(2):
            revisar_horas(created.registro.id, payload, self.db, self.users["supervisor"])
        self.assertEqual(self.db.get(Practica, "p1").horas_acumuladas, 0)
        self.expect_status(409, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO"), self.db, self.users["supervisor"])

    def test_resource_permissions_and_supervisor_scope(self):
        created = self.submit()
        for name in ["other", "otherteacher", "foreignsupervisor"]:
            self.expect_status(404, get_horas, "p1", self.db, self.users[name])
        for name in ["student", "teacher", "admin"]:
            self.expect_status(403, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO"), self.db, self.users[name])
        self.expect_status(404, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO"), self.db, self.users["foreignsupervisor"])
        self.expect_status(403, cerrar_practica, "p1", self.db, self.users["supervisor"])
        self.expect_status(404, cerrar_practica, "p1", self.db, self.users["otherteacher"])
        self.expect_status(404, generar_reporte, "p2", self.db, self.users["supervisor"])
        self.assertEqual(historial("other", self.db, self.users["supervisor"]), [])

    def test_input_validation(self):
        for hours in [0, 25, 1.5, True]:
            with self.assertRaises(ValidationError):
                RegistrarHorasRequest(horas=hours, descripcion="Actividad")
        with self.assertRaises(ValidationError):
            RegistrarHorasRequest(horas=1, descripcion="   ")
        for value in ["2026-02-30", "2999-01-01", "no-fecha"]:
            self.expect_status(422, registrar_horas, "p1", RegistrarHorasRequest(horas=1, descripcion="Actividad", fecha=value), self.db, self.users["student"])


if __name__ == "__main__":
    unittest.main()
