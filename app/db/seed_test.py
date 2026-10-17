"""Datos ficticios: se ejecutan solo desde bootstrap_test sobre ssp_test."""
from datetime import datetime, timedelta, timezone
from app.core.security import hash_password
from app.models.models import (
    Aula, AulaEstadoEnum, Empresa, Entrega, EntregaEstadoEnum, Inscripcion,
    Notificacion, NotificacionTipoEnum, Practica, PracticaEstadoEnum,
    RegistroHoras, RegistroHorasEstadoEnum, RoleEnum, Supervisor, Tarea, User,
)

ACCOUNTS = [
    ("admin", RoleEnum.ADMIN), ("profesor", RoleEnum.PROFESOR),
    ("alumno", RoleEnum.ALUMNO), ("supervisor", RoleEnum.SUPERVISOR),
    ("profesor2", RoleEnum.PROFESOR), ("alumno2", RoleEnum.ALUMNO),
]


def seed(db, password):
    if len(password) < 24:
        raise ValueError("TEST_SEED_PASSWORD debe tener al menos 24 caracteres.")
    allowed = {f"test-{name}" for name, _ in ACCOUNTS}
    if any(row[0] not in allowed for row in db.query(User.id).all()):
        raise ValueError("El esquema contiene usuarios ajenos a esta semilla; no se modifica.")
    hashed = hash_password(password)
    for name, role in ACCOUNTS:
        if not db.get(User, f"test-{name}"):
            db.add(User(id=f"test-{name}", nombres=name.capitalize(), apellidos="Prueba", email=f"{name}.prueba@unsa.edu.pe", hashed_password=hashed, role=role))
    db.flush()
    now = datetime.now(timezone.utc)
    for suffix, teacher, student in [("1", "profesor", "alumno"), ("2", "profesor2", "alumno2")]:
        aula_id, empresa_id, practica_id, tarea_id = (f"test-{kind}-{suffix}" for kind in ["aula", "empresa", "practica", "tarea"])
        if not db.get(Aula, aula_id):
            db.add(Aula(id=aula_id, nombre=f"Comunicación · Pruebas {suffix}", codigo=f"TEST-COM-{suffix}", descripcion="Aula ficticia para desarrollo.", periodo="PRUEBAS", profesor_id=f"test-{teacher}", estado=AulaEstadoEnum.ACTIVA, inscritos=1))
        if not db.get(Empresa, empresa_id):
            db.add(Empresa(id=empresa_id, practicante_id=f"test-{student}", razon_social=f"Centro ficticio {suffix}", ruc=f"0000000000{suffix}", direccion="Dirección ficticia", sector="Comunicación", telefono="000000000", email=f"centro{suffix}@example.invalid"))
        db.flush()
        if not db.get(Inscripcion, f"test-inscripcion-{suffix}"):
            db.add(Inscripcion(id=f"test-inscripcion-{suffix}", alumno_id=f"test-{student}", aula_id=aula_id, progreso=0, semana_actual=1, semanas_totales=16))
        if not db.get(Practica, practica_id):
            db.add(Practica(id=practica_id, practicante_id=f"test-{student}", aula_id=aula_id, periodo="PRUEBAS", empresa_id=empresa_id, horas_acumuladas=0, horas_minimas=360, estado=PracticaEstadoEnum.EN_CURSO, fecha_inicio=now))
        if not db.get(Tarea, tarea_id):
            db.add(Tarea(id=tarea_id, aula_id=aula_id, titulo="Informe de prueba", descripcion="Contenido ficticio para comprobar revisión y calificación.", fecha_limite=now + timedelta(days=7)))
        db.flush()
        if not db.get(Entrega, f"test-entrega-{suffix}"):
            db.add(Entrega(id=f"test-entrega-{suffix}", tarea_id=tarea_id, alumno_id=f"test-{student}", descripcion="Entrega ficticia de prueba.", comentario="Sin archivos reales.", estado=EntregaEstadoEnum.ENTREGADA))
        if not db.get(Notificacion, f"test-aviso-{suffix}"):
            db.add(Notificacion(id=f"test-aviso-{suffix}", user_id=f"test-{student}", tipo=NotificacionTipoEnum.TAREA_ASIGNADA, titulo="Entorno de prueba preparado", mensaje="Estos datos son ficticios y se pueden modificar durante el desarrollo.", leida=0))
    if not db.get(Supervisor, "test-supervisor-contacto"):
        db.add(Supervisor(id="test-supervisor-contacto", empresa_id="test-empresa-1", user_id="test-supervisor", nombres="Supervisor", apellidos="Prueba", cargo="Responsable de pruebas", email="supervisor.prueba@unsa.edu.pe", telefono="000000000"))
    # Se deja una práctica activa sin horas para probar el circuito desde cero.
    db.flush()
