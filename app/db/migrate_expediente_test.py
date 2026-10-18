"""Migración aditiva del incremento 18, limitada al Supabase de pruebas."""
import sys
from sqlalchemy import text
from app.core.config import settings
from app.db.test_environment import check_test_target


def run():
    check_test_target(settings)
    from app.db.session import engine
    from app.models.models import ExpedientePractica
    with engine.begin() as conn:
        if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
            raise ValueError("Esquema no autorizado.")
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("ALTER TABLE ssp_test.evaluaciones ADD COLUMN IF NOT EXISTS contenido TEXT"))
        ExpedientePractica.__table__.create(bind=conn, checkfirst=True)
        conn.execute(text("ALTER TABLE ssp_test.expedientes_practicas ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("REVOKE ALL ON TABLE ssp_test.expedientes_practicas FROM PUBLIC, anon, authenticated"))
    print("OK: evaluación y expediente preparados en ssp_test; no se modificaron datos académicos.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("No se aplicó la migración de expediente. Revisa el entorno de pruebas; credenciales omitidas.", file=sys.stderr)
        sys.exit(1)
