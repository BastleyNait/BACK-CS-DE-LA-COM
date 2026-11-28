"""Crea la tabla suscripciones_push en el esquema configurado (idempotente; no toca otras tablas)."""
import json
from sqlalchemy import inspect, text
from app.core.config import settings
from app.db.session import engine
from app.models.models import SuscripcionPush


def main():
    schema = settings.DATABASE_SCHEMA
    table = SuscripcionPush.__table__
    with engine.begin() as conn:
        if conn.execute(text("select current_schema()")).scalar_one() != schema:
            raise SystemExit("El esquema activo no coincide con DATABASE_SCHEMA.")
        existed = inspect(conn).has_table(table.name, schema=schema)
        table.create(conn, checkfirst=True)
        if conn.dialect.name == "postgresql":
            conn.execute(text(f'ALTER TABLE "{schema}".suscripciones_push ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'REVOKE ALL ON "{schema}".suscripciones_push FROM PUBLIC, anon, authenticated'))
    print(json.dumps({"schema": schema, "table": table.name, "created": not existed}))


if __name__ == "__main__":
    main()
