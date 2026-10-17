from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings

url = settings.DATABASE_URL
if url.startswith("postgres://"):
    url = "postgresql://" + url[11:]
# En pruebas: SSL y timeout acotado. El pooler mantiene las conexiones de Postgres.
connect_args = {"sslmode": "require", "connect_timeout": 10} if settings.DATABASE_SCHEMA != "public" else {}
engine = create_engine(url, pool_pre_ping=True, poolclass=NullPool, connect_args=connect_args, hide_parameters=True)

if settings.DATABASE_SCHEMA != "public":
    @event.listens_for(engine, "connect", insert=True)
    def set_schema(dbapi_connection, connection_record):
        # Antes de la introspeccion del dialecto y fuera de una transaccion:
        # no se revierte tras rollback ni consulta tablas de public por fallback.
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        try:
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f'SET SESSION search_path TO "{settings.DATABASE_SCHEMA}"')
        finally:
            dbapi_connection.autocommit = previous

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
