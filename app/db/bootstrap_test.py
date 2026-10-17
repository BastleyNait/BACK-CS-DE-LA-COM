"""Preparación explícita e idempotente del Supabase de prueba autorizado."""
import argparse
import sys
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.db.test_environment import check_test_target


def run(check=False):
    url = check_test_target(settings)
    bootstrap_engine = create_engine(url, poolclass=NullPool, connect_args={"sslmode": "require", "connect_timeout": 10}, hide_parameters=True)
    try:
        with bootstrap_engine.begin() as conn:
            if not check:
                conn.execute(text('CREATE SCHEMA IF NOT EXISTS "ssp_test"'))
                conn.execute(text('REVOKE ALL ON SCHEMA "ssp_test" FROM PUBLIC, anon, authenticated'))
        from app.db.session import Base, engine, SessionLocal
        from app.models import models  # registra todos los modelos
        if not check:
            with engine.begin() as conn:
                Base.metadata.create_all(bind=conn)
                for table in Base.metadata.sorted_tables:
                    name = conn.dialect.identifier_preparer.quote(table.name)
                    conn.execute(text(f'ALTER TABLE "ssp_test".{name} ENABLE ROW LEVEL SECURITY'))
                conn.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA "ssp_test" FROM PUBLIC, anon, authenticated'))
                conn.execute(text('REVOKE ALL ON ALL SEQUENCES IN SCHEMA "ssp_test" FROM PUBLIC, anon, authenticated'))
            from app.db.seed_test import seed
            with SessionLocal.begin() as db:
                seed(db, settings.TEST_SEED_PASSWORD.get_secret_value())
        with engine.connect() as conn:
            if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
                raise ValueError("La conexión no quedó aislada en ssp_test.")
            if not set(Base.metadata.tables).issubset(inspect(conn).get_table_names(schema="ssp_test")):
                raise ValueError("Faltan tablas; ejecuta bootstrap_test sin --check.")
        print("OK: Supabase de prueba accesible, esquema ssp_test y tablas disponibles.")
    finally:
        bootstrap_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Solo comprobar; no crea ni modifica datos.")
    args = parser.parse_args()
    try:
        run(args.check)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("No se pudo completar la conexión o preparación. Revisa DATABASE_URL, contraseña, SSL y conectividad; no se muestran credenciales.", file=sys.stderr)
        sys.exit(1)
