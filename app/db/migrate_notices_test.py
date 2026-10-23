"""Destinos y tipos de avisos; solo base de pruebas autorizada, sin semillas."""
import sys
from sqlalchemy import text
from app.core.config import settings
from app.db.test_environment import check_test_target


def run():
    check_test_target(settings)
    from app.db.session import engine
    with engine.begin() as conn:
        if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
            raise ValueError("Esquema no autorizado.")
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text("SET LOCAL statement_timeout = '30s'"))
        conn.execute(text("ALTER TABLE ssp_test.notificaciones ADD COLUMN IF NOT EXISTS destino JSONB"))
        for value in ("TAREA_ACTUALIZADA", "REVISION_HORAS"):
            conn.execute(text(f"ALTER TYPE ssp_test.notificaciontipoenum ADD VALUE IF NOT EXISTS '{value}'"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notificaciones_usuario_fecha_id ON ssp_test.notificaciones (user_id, fecha DESC, id DESC)"))
        conn.execute(text("ALTER TABLE ssp_test.notificaciones ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("REVOKE ALL ON TABLE ssp_test.notificaciones FROM PUBLIC, anon, authenticated"))
    print("OK: destinos de avisos preparados en ssp_test; sin semillas ni cambios académicos.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("No se aplicó la migración de avisos. Revisa el entorno; credenciales omitidas.", file=sys.stderr)
        sys.exit(1)
