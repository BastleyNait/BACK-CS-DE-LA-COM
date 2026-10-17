"""Incremento 13: migración aditiva, solo para el Supabase de pruebas autorizado."""
import sys
from sqlalchemy import text, inspect
from app.core.config import settings
from app.db.test_environment import check_test_target


def run():
    check_test_target(settings)
    from app.db.session import engine
    from app.models.models import HistorialHoras
    with engine.begin() as conn:
        if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
            raise ValueError("La conexión no está aislada en ssp_test.")
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text('ALTER TABLE ssp_test.registro_horas ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)'))
        conn.execute(text("ALTER TABLE ssp_test.registro_horas ADD COLUMN IF NOT EXISTS observacion TEXT NOT NULL DEFAULT ''"))
        HistorialHoras.__table__.create(bind=conn, checkfirst=True)
        conn.execute(text('ALTER TABLE ssp_test.historial_horas ENABLE ROW LEVEL SECURITY'))
        conn.execute(text('REVOKE ALL ON TABLE ssp_test.historial_horas FROM PUBLIC, anon, authenticated'))
        columns = {c['name'] for c in inspect(conn).get_columns('registro_horas', schema='ssp_test')}
        assert {'revision', 'observacion'}.issubset(columns)
        assert conn.execute(text("SELECT relrowsecurity FROM pg_class WHERE oid = 'ssp_test.historial_horas'::regclass")).scalar_one()
        for role in ('anon', 'authenticated'):
            assert not conn.execute(text("SELECT has_schema_privilege(:role, 'ssp_test', 'USAGE') OR has_table_privilege(:role, 'ssp_test.historial_horas', 'SELECT,INSERT,UPDATE,DELETE')"), {'role': role}).scalar_one()
    print("OK: revisión, observación e historial preparados; RLS y aislamiento comprobados.")


if __name__ == '__main__':
    try:
        run()
    except Exception:
        print("No se aplicó la migración de horas. Revisa entorno y conexión; no se muestran credenciales.", file=sys.stderr)
        sys.exit(1)
