"""Regresión del circuito de horas; SQLite aislado, sin tocar Supabase."""
import unittest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models.models import User, RoleEnum, Aula, Empresa, Supervisor, Practica, RegistroHoras, HistorialHoras, Auditoria, PracticaEstadoEnum
from app.routers.practicas import registrar_horas, get_horas, cerrar_practica, historial, generar_reporte, corregir_horas, historial_horas
from app.routers.empresa import revisar_horas
from app.schemas.schemas import RegistrarHorasRequest, RevisarHorasRequest, CorregirHorasRequest


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
        payload = RevisarHorasRequest(estadoValidacion="VALIDADO", revision=0)
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
        payload = RevisarHorasRequest(estadoValidacion="RECHAZADO", revision=0, observacion="Detalla el trabajo realizado")
        for _ in range(2):
            revisar_horas(created.registro.id, payload, self.db, self.users["supervisor"])
        self.assertEqual(self.db.get(Practica, "p1").horas_acumuladas, 0)
        self.expect_status(409, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO", revision=0), self.db, self.users["supervisor"])

    def test_resource_permissions_and_supervisor_scope(self):
        created = self.submit()
        for name in ["other", "otherteacher", "foreignsupervisor"]:
            self.expect_status(404, get_horas, "p1", self.db, self.users[name])
        for name in ["student", "teacher", "admin"]:
            self.expect_status(403, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO", revision=0), self.db, self.users[name])
        self.expect_status(404, revisar_horas, created.registro.id, RevisarHorasRequest(estadoValidacion="VALIDADO", revision=0), self.db, self.users["foreignsupervisor"])
        self.expect_status(403, cerrar_practica, "p1", self.db, self.users["supervisor"])
        self.expect_status(404, cerrar_practica, "p1", self.db, self.users["otherteacher"])
        self.expect_status(404, generar_reporte, "p2", self.db, self.users["supervisor"])
        self.assertEqual(historial("other", self.db, self.users["supervisor"]), [])

    def test_rejection_correction_history_and_stale_review(self):
        created = self.submit().registro
        rejected = revisar_horas(created.id, RevisarHorasRequest(estadoValidacion="RECHAZADO", revision=0, observacion="  Detalla la entrevista  "), self.db, self.users["supervisor"])
        self.assertEqual((rejected.revision, rejected.observacion), (1, "Detalla la entrevista"))
        correction = CorregirHorasRequest(revision=1, fecha=created.fecha[:10], horas=3, descripcion="Entrevista corregida")
        for _ in range(2):
            corrected = corregir_horas("p1", created.id, correction, self.db, self.users["student"])
            self.assertEqual((corrected.revision, corrected.estadoValidacion, corrected.observacion), (2, "PENDIENTE", ""))
        self.assertEqual(self.db.get(Practica, "p1").horas_acumuladas, 0)
        self.expect_status(409, revisar_horas, created.id, RevisarHorasRequest(estadoValidacion="VALIDADO", revision=0), self.db, self.users["supervisor"])
        revisar_horas(created.id, RevisarHorasRequest(estadoValidacion="VALIDADO", revision=2), self.db, self.users["supervisor"])
        self.assertEqual(self.db.get(Practica, "p1").horas_acumuladas, 3)
        self.expect_status(409, corregir_horas, "p1", created.id, correction, self.db, self.users["student"])
        events = historial_horas("p1", created.id, self.db, self.users["student"])
        self.assertEqual([e.accion for e in events], ["REGISTRO", "RECHAZO", "CORRECCION", "VALIDACION"])
        self.assertEqual(events[2].antes.observacion, "Detalla la entrevista")
        self.assertEqual((events[2].antes.horas, events[2].despues.horas), (2, 3))
        self.assertEqual(self.db.query(HistorialHoras).count(), 4)
        self.assertEqual(self.db.query(Auditoria).count(), 4)
        self.expect_status(404, historial_horas, "p1", created.id, self.db, self.users["other"])

    def test_correction_permissions_unchanged_payload_and_closed_practice(self):
        created = self.submit().registro
        payload = CorregirHorasRequest(revision=0, fecha=created.fecha[:10], horas=3, descripcion="Corrección")
        self.expect_status(409, corregir_horas, "p1", created.id, payload, self.db, self.users["student"])
        for name in ["supervisor", "teacher", "admin"]:
            self.expect_status(403, corregir_horas, "p1", created.id, payload, self.db, self.users[name])
        self.expect_status(404, corregir_horas, "p1", created.id, payload, self.db, self.users["other"])
        self.expect_status(404, corregir_horas, "p1", "missing", payload, self.db, self.users["student"])
        revisar_horas(created.id, RevisarHorasRequest(estadoValidacion="RECHAZADO", revision=0, observacion="Revisar"), self.db, self.users["supervisor"])
        unchanged = CorregirHorasRequest(revision=1, fecha=created.fecha[:10], horas=created.horas, descripcion=created.descripcion)
        self.expect_status(422, corregir_horas, "p1", created.id, unchanged, self.db, self.users["student"])
        self.db.get(Practica, "p1").estado = PracticaEstadoEnum.CERRADA
        self.db.commit()
        self.expect_status(409, corregir_horas, "p1", created.id, payload.model_copy(update={"revision": 1}), self.db, self.users["student"])
        self.assertEqual(self.db.query(HistorialHoras).count(), 2)

    def test_rejection_requires_reason_and_review_revision(self):
        for value in ["", "  "]:
            with self.assertRaises(ValidationError):
                RevisarHorasRequest(estadoValidacion="RECHAZADO", revision=0, observacion=value)
        for revision in [True, -1, 0.5]:
            with self.assertRaises(ValidationError):
                RevisarHorasRequest(estadoValidacion="VALIDADO", revision=revision)
        with self.assertRaises(ValidationError):
            RevisarHorasRequest(estadoValidacion="VALIDADO")

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
