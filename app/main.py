from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, aulas

app = FastAPI(
    title="SSP — Sistema de Seguimiento de Practicantes",
    description="Backend FastAPI para el SSP (UNSA, FIPS — Grupo 7).",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(aulas.router, prefix=API_PREFIX)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "app": "SSP Backend"}
