from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# SQLite (desarrollo) necesita check_same_thread=False para el pool de hilos de
# FastAPI. Para PostgreSQL (equipo/producción) no se pasa connect_args especial.
_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)
engine = create_engine(
    settings.DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency que provee una sesión de BD por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
