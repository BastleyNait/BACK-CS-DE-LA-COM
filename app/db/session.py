from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# SQLite (desarrollo) necesita check_same_thread=False para el pool de hilos de
# FastAPI. Para PostgreSQL (equipo/producción) no se pasa connect_args especial.
_connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

# NullPool: en serverless (Vercel) cada invocación puede correr en un contenedor
# distinto. Mantener un pool de conexiones por contenedor agota rápidamente los
# slots de Postgres. Con NullPool se abre/cierra una conexión por request y se
# delega el pooling al pooler externo (Supabase Supavisor / PgBouncer, puerto
# 6543 en modo transaction). pool_pre_ping descarta conexiones muertas.
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
    **({} if _is_sqlite else {"poolclass": NullPool}),
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
