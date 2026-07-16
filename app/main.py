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
    metas,
    notificaciones,
    practicas,
    profesor,
    tareas,
)

from app.db.session import engine, Base
# Crear tablas si no existen al iniciar la aplicación (útil para serverless en Vercel)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SSP — Sistema de Seguimiento de Practicantes",
    description="Backend FastAPI para el SSP (UNSA, FIPS — Grupo 7).",
    version="1.0.0",
)

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
app.include_router(practicas.router, prefix=API_PREFIX)
app.include_router(notificaciones.router, prefix=API_PREFIX)
app.include_router(metas.router, prefix=API_PREFIX)
app.include_router(comunicacion.router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "app": "SSP Backend"}
