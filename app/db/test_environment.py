"""Límites del entorno autorizado de pruebas; nunca muestra credenciales."""
import re
from sqlalchemy.engine import make_url


def check_test_target(settings):
    if settings.APP_ENV not in {"development", "test"}:
        raise ValueError("APP_ENV debe ser development o test.")
    if settings.DATABASE_SCHEMA != "ssp_test":
        raise ValueError("Las pruebas solo pueden usar el esquema ssp_test.")
    project = settings.TEST_DATABASE_PROJECT_REF
    if not re.fullmatch(r"[a-z]{20}", project):
        raise ValueError("Completa TEST_DATABASE_PROJECT_REF con el proyecto de prueba.")
    if not settings.DATABASE_URL:
        raise ValueError("Completa DATABASE_URL en el archivo .env local.")
    try:
        value = settings.DATABASE_URL
        url = make_url("postgresql://" + value[11:] if value.startswith("postgres://") else value)
        direct = url.host == f"db.{project}.supabase.co" and url.username == "postgres"
        pooled = bool(url.host and url.host.endswith(".pooler.supabase.com")) and url.username == f"postgres.{project}"
        valid = url.get_backend_name() == "postgresql" and url.port == 5432 and url.database == "postgres" and (direct or pooled) and url.password and "[" not in url.password
    except Exception:
        valid = False
    if not valid:
        raise ValueError("DATABASE_URL debe apuntar al proyecto de prueba indicado, usando conexión directa o Session pooler en 5432, con contraseña completa.")
    return url
