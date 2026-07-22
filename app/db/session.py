from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# NullPool: en serverless (Vercel) cada invocación puede correr en una
# instancia distinta y no hay garantía de reuso del proceso, así que un pool
# tradicional (QueuePool) solo acumula conexiones muertas y termina agotando
# el límite del pooler de Supabase. Con NullPool cada request abre y cierra
# su propia conexión, dejando que el pooler (modo Transaction, puerto 6543)
# gestione el pooling real.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, poolclass=NullPool)
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
