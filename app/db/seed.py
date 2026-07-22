"""
Script de semilla — inserta los usuarios iniciales del mockDb.
Úsalo una sola vez después de crear las tablas:
    python -m app.db.seed
"""

from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.models import Aula, AulaEstadoEnum, Base, RoleEnum, User
from datetime import datetime, timezone


def seed():
    # Crea tablas si no existen (alternativa a Alembic para desarrollo rápido)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("Base de datos ya tiene datos. Semilla omitida.")
            return

        # ── Usuarios semilla (idénticos al mockDb del frontend) ────────────────
        admin = User(
            id="u-admin",
            nombres="Gabriel",
            apellidos="Llerena",
            email="admin@unsa.edu.pe",
            hashed_password=hash_password("admin123"),
            role=RoleEnum.ADMIN,
        )
        profesor = User(
            id="u-prof",
            nombres="Jose Luis",
            apellidos="Cuenca",
            email="profesor@unsa.edu.pe",
            hashed_password=hash_password("profesor123"),
            role=RoleEnum.PROFESOR,
        )
        alumno = User(
            id="u-alumno",
            nombres="Piero",
            apellidos="Mejía",
            email="alumno@unsa.edu.pe",
            hashed_password=hash_password("alumno123"),
            role=RoleEnum.ALUMNO,
        )
        db.add_all([admin, profesor, alumno])
        db.flush()  # necesario para FK en aulas

        # ── Aulas semilla ──────────────────────────────────────────────────────
        aula1 = Aula(
            id="a-1",
            nombre="Prácticas Pre-Profesionales I",
            codigo="PP-2026-I",
            descripcion="Seguimiento de prácticas en empresas convenio. Registro de asistencia e informes semanales.",
            periodo="2026-I",
            profesor_id="u-prof",
            estado=AulaEstadoEnum.ACTIVA,
            inscritos=18,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        aula2 = Aula(
            id="a-2",
            nombre="Taller de Comunicación Audiovisual",
            codigo="TCA-2025-II",
            descripcion="Curso concluido del periodo anterior.",
            periodo="2025-II",
            profesor_id="u-prof",
            estado=AulaEstadoEnum.CONCLUIDA,
            inscritos=24,
            created_at=datetime(2025, 8, 15, tzinfo=timezone.utc),
        )
        db.add_all([aula1, aula2])
        db.commit()
        print("✅ Semilla insertada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
