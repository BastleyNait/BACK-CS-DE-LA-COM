from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    admin,
    alumno,
    archivos,
    aulas,
    auth,
    comunicacion,
    empresa,
    expedientes,
    metas,
    notificaciones,
    practicas,
    profesor,
    tareas,
)

from app.db.session import engine, Base
# Crear tablas si no existen al iniciar la aplicación (útil para serverless en Vercel)
if settings.AUTO_CREATE_TABLES:
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SSP — Sistema de Seguimiento de Practicantes",
    description="Backend FastAPI para el SSP (UNSA, FIPS — Grupo 7).",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(aulas.router, prefix=API_PREFIX)
app.include_router(alumno.router, prefix=API_PREFIX)
app.include_router(archivos.router, prefix=API_PREFIX)
app.include_router(tareas.router, prefix=API_PREFIX)
app.include_router(profesor.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(empresa.router, prefix=API_PREFIX)
app.include_router(expedientes.router, prefix=API_PREFIX)
app.include_router(practicas.router, prefix=API_PREFIX)
app.include_router(notificaciones.router, prefix=API_PREFIX)
app.include_router(metas.router, prefix=API_PREFIX)
app.include_router(comunicacion.router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "app": "SSP Backend"}


if settings.APP_ENV in {"development", "test"}:
    @app.get("/dev/ready", tags=["development"])
    def test_readiness():
        from fastapi import HTTPException
        from sqlalchemy import text
        from app.db.test_environment import check_test_target
        try:
            check_test_target(settings)
            with engine.connect() as conn:
                if conn.execute(text("select current_schema()")).scalar_one() != "ssp_test":
                    raise ValueError("Esquema incorrecto.")
                conn.execute(text("select 1 from users limit 1"))
            return {"status": "ok", "environment": settings.APP_ENV, "schema": "ssp_test", "database": "reachable"}
        except Exception:
            raise HTTPException(status_code=503, detail="La base de prueba no esta preparada o no responde.") from None
