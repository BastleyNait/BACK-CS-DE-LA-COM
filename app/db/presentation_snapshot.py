"""Copia privada de datos ficticios para una entrega; nunca reemplaza un esquema."""
import argparse
import json
import secrets
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sqlalchemy import MetaData, Enum, String, cast, insert, select, text, func, and_, or_, exists
from app.core.config import settings
from app.db.test_environment import check_test_target

SCHEMA = "ssp_presentacion_20261023"
VERSION = "0.2.0-avance.20261023"
WEB_PROJECT = "practicascc-avance-23oct-2026"
API_PROJECT = "practicascc-api-avance-23oct-2026"
EXCLUDED = {"identidades_google", "recuperaciones_cuentas", "auditoria"}
PHASE = 'preflight'


def isolated_metadata(source):
    target = MetaData(schema=SCHEMA)
    for table in source.sorted_tables:
        table.to_metadata(target, schema=SCHEMA, referred_schema_fn=lambda *args: SCHEMA)
    for table in target.sorted_tables:
        original = source.tables[table.name]
        for column in table.c:
            if isinstance(column.type, Enum):
                if column.type is original.c[column.name].type:
                    raise ValueError("El tipo del destino no está aislado.")
                column.type.schema = SCHEMA
        if any(fk.column.table.schema != SCHEMA for fk in table.foreign_keys):
            raise ValueError("Una referencia del destino no está aislada.")
    return target


def copy_selection(original, dest, metadata, allowed_ids):
    values = [cast(cast(original.c[col.name], String), col.type) if isinstance(col.type, Enum) else original.c[col.name] for col in dest.c]
    query = select(*values)
    if original.name == 'users':
        query = query.where(original.c.id.in_(allowed_ids))
    for constraint in original.foreign_key_constraints:
        parent_name = next(iter(constraint.elements)).column.table.name
        parent = metadata.tables[f'{SCHEMA}.{parent_name}']
        matches = [parent.c[fk.column.name] == original.c[fk.parent.name] for fk in constraint.elements]
        nullable = [original.c[fk.parent.name].is_(None) for fk in constraint.elements]
        query = query.where(or_(*nullable, exists(select(1).select_from(parent).where(and_(*matches)))))
    return query


def create_snapshot(config_path):
    global PHASE
    check_test_target(settings)
    from app.db.session import Base, engine
    from app.models import models
    from app.core.security import hash_password
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("DATABASE_SCHEMA") != SCHEMA:
            raise ValueError("El archivo de configuración no corresponde a esta entrega.")
    else:
        config = {"DATABASE_URL": settings.DATABASE_URL, "DATABASE_SCHEMA": SCHEMA,
            "SECRET_KEY": secrets.token_urlsafe(48), "APP_ENV": "test", "AUTO_CREATE_TABLES": "false",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "720", "PRESENTATION_VERSION": VERSION,
            "CORS_ORIGINS": f"https://{WEB_PROJECT}.vercel.app,http://localhost:5174",
            "GOOGLE_CLIENT_IDS": "", "SMTP_HOST": "", "TEST_DATABASE_PROJECT_REF": settings.TEST_DATABASE_PROJECT_REF,
            "DEMO_PASSWORD": secrets.token_urlsafe(15), "WEB_PROJECT": WEB_PROJECT, "API_PROJECT": API_PROJECT}
        # Se conserva antes de la transacción para poder reanudar sin perder los accesos.
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    metadata = isolated_metadata(Base.metadata)
    password_hash = hash_password(config["DEMO_PASSWORD"])
    totals = {}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
                raise ValueError("Origen no autorizado.")
            if conn.execute(text("select 1 from pg_namespace where nspname=:name"), {"name": SCHEMA}).first():
                raise ValueError("La versión de presentación ya existe; no se reemplazó.")
            PHASE = 'cuentas_ficticias'
            accounts = conn.execute(select(models.User.id, models.User.email)).all()
            allowed_ids = {row.id for row in accounts if row.email.endswith('.prueba@unsa.edu.pe') or row.email.startswith('gestion.') and row.email.endswith('@unsa.edu.pe')}
            if len(allowed_ids) < 6:
                raise ValueError("Faltan las cuentas ficticias del recorrido.")
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '90s'"))
            PHASE = 'estructura'
            conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
            conn.execute(text(f'REVOKE ALL ON SCHEMA "{SCHEMA}" FROM PUBLIC, anon, authenticated'))
            metadata.create_all(conn)
            for original in Base.metadata.sorted_tables:
                PHASE = 'copiar_' + original.name
                dest = metadata.tables[f"{SCHEMA}.{original.name}"]
                if original.name not in EXCLUDED:
                    conn.execute(insert(dest).from_select([col.name for col in dest.c], copy_selection(original,dest,metadata,allowed_ids)))
                totals[original.name] = conn.execute(select(func.count()).select_from(dest)).scalar_one()
            users = metadata.tables[f"{SCHEMA}.users"]
            conn.execute(users.update().values(hashed_password=password_hash))
            PHASE = 'ejemplos_de_revision'
            add_review_examples(conn, metadata)
            for table in metadata.sorted_tables:
                name = conn.dialect.identifier_preparer.quote(table.name)
                conn.execute(text(f'ALTER TABLE "{SCHEMA}".{name} ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{SCHEMA}" FROM PUBLIC, anon, authenticated'))
            conn.execute(text(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA "{SCHEMA}" FROM PUBLIC, anon, authenticated'))
            foreign = conn.execute(text("""select count(*) from pg_constraint c
                join pg_class t on t.oid=c.conrelid join pg_namespace n on n.oid=t.relnamespace
                join pg_class r on r.oid=c.confrelid join pg_namespace rn on rn.oid=r.relnamespace
                where c.contype='f' and n.nspname=:target and rn.nspname<>:target"""), {"target":SCHEMA}).scalar_one()
            if foreign: raise ValueError("La copia conserva referencias al origen.")
    report = {"created":True,"schema":SCHEMA,"version":VERSION,"copiedTables":len(totals),"copiedRows":totals,
        "excludedNonDemoAccounts":len(accounts)-len(allowed_ids),"sourceModified":False,"newCredentials":True,"googleEnabled":False}
    path.with_name("snapshot-verificacion.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"created":True,"schema":SCHEMA,"copiedTables":len(totals),"sourceModified":False,"credentialsPrinted":False}))


def add_review_examples(conn, metadata):
    def table(name): return metadata.tables[f"{SCHEMA}.{name}"]
    users = table("users")
    student = conn.execute(select(users.c.id).where(users.c.email == 'alumno.prueba@unsa.edu.pe')).scalar_one()
    teacher = conn.execute(select(users.c.id).where(users.c.email == 'profesor.prueba@unsa.edu.pe')).scalar_one()
    aula = conn.execute(select(table('aulas').c.id).join(table('inscripciones'), table('inscripciones').c.aula_id == table('aulas').c.id).where(
        table('aulas').c.profesor_id == teacher, table('inscripciones').c.alumno_id == student, table('aulas').c.estado == 'ACTIVA')).scalars().first()
    if not aula: raise ValueError('No hay aula ficticia activa para el recorrido.')
    due = datetime.now(timezone.utc) + timedelta(days=14)
    for suffix,title in [('pendiente','Demostración · Informe semanal'),('revision','Demostración · Crónica para revisión')]:
        task_id = f'presentacion-{suffix}-20261023'
        conn.execute(table('tareas').insert().values(id=task_id,aula_id=aula,titulo=title,
            descripcion='Contenido ficticio para revisar el avance. Describe las actividades, los resultados y las fuentes utilizadas.',fecha_limite=due))
        conn.execute(table('notificaciones').insert().values(id=f'presentacion-aviso-{suffix}',user_id=student,tipo='TAREA_ASIGNADA',
            titulo='Nueva tarea de demostración',mensaje=title,destino={'tipo':'TAREA','aulaId':aula,'tareaId':task_id},leida=0))
        if suffix == 'revision':
            conn.execute(table('entregas').insert().values(id='presentacion-entrega-20261023',tarea_id=task_id,alumno_id=student,
                descripcion='Crónica ficticia preparada para revisar el circuito de calificación del docente.',comentario='Datos de presentación.',estado='ENTREGADA'))
    practice = conn.execute(select(table('practicas').c.id).where(table('practicas').c.practicante_id == student,
        table('practicas').c.estado != 'CERRADA')).scalars().first()
    if practice:
        conn.execute(table('registro_horas').insert().values(id='presentacion-horas-20261023',practica_id=practice,
            fecha=datetime.now(timezone.utc),horas=2,descripcion='Demostración · producción de contenido institucional.',estado_validacion='PENDIENTE'))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config-output',required=True)
    args=parser.parse_args()
    try:
        create_snapshot(args.config_output)
    except Exception as error:
        print(json.dumps({"created":False,"errorType":type(error).__name__,"phase":PHASE,"sqlstate":getattr(getattr(error,'orig',None),'pgcode',None),"message":"No se creó ni reemplazó la copia. Revisar el entorno autorizado; credenciales omitidas."}),file=sys.stderr)
        sys.exit(1)
