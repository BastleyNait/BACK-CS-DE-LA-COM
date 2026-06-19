from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# NullPool: en serverless (Vercel) cada invocación puede correr en un contenedor
# distinto. Mantener un pool de conexiones por contenedor agota rápidamente los
# slots de Postgres. Con NullPool se abre/cierra una conexión por request y se
# delega el pooling al pooler externo (Supabase Supavisor / PgBouncer, puerto
# 6543 en modo transaction). pool_pre_ping descarta conexiones muertas.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    poolclass=NullPool,
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
