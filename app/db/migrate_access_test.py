"""Migración aditiva y acotada de acceso; no carga semillas."""
import sys
from sqlalchemy import text, inspect
from app.core.config import settings
from app.db.test_environment import check_test_target


def run():
    check_test_target(settings)
    from app.db.session import engine
    from app.models.models import IdentidadGoogle, SeguridadCuenta, RecuperacionCuenta, ContenidoArchivo, VersionEntrega, CambioTarea
    with engine.begin() as conn:
        if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
            raise ValueError("Esquema no autorizado.")
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        for model in (IdentidadGoogle, SeguridadCuenta, RecuperacionCuenta, ContenidoArchivo, VersionEntrega, CambioTarea):
            model.__table__.create(conn, checkfirst=True)
            name = model.__tablename__
            conn.execute(text(f'ALTER TABLE ssp_test.{name} ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'REVOKE ALL ON TABLE ssp_test.{name} FROM PUBLIC, anon, authenticated'))
        conn.execute(text('ALTER TABLE ssp_test.contenidos_archivos ADD COLUMN IF NOT EXISTS material INTEGER NOT NULL DEFAULT 0'))
        inspector = inspect(conn)
        quote = conn.dialect.identifier_preparer.quote
        for constraint in inspector.get_unique_constraints("supervisores", schema="ssp_test"):
            if constraint["column_names"] == ["user_id"]:
                conn.execute(text(f'ALTER TABLE ssp_test.supervisores DROP CONSTRAINT {quote(constraint["name"])}'))
        for index in inspector.get_indexes("supervisores", schema="ssp_test"):
            if index.get("unique") and index["column_names"] == ["user_id"] and not index.get("duplicates_constraint"):
                conn.execute(text(f'DROP INDEX ssp_test.{quote(index["name"])}'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_supervisores_user_id ON ssp_test.supervisores (user_id)'))
    print("OK: acceso, documentos y revisiones privados preparados en ssp_test; sin semillas.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("No se aplicó la migración de acceso; revisa el entorno. Credenciales omitidas.", file=sys.stderr)
        sys.exit(1)
