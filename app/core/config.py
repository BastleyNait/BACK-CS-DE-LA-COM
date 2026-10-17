import json
import os
import re
from pydantic_settings import BaseSettings
from typing import List, Literal
from pydantic import SecretStr, field_validator


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ssp_db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # str (no List[str]): pydantic-settings hace json.loads() sobre los campos
    # lista al leer env vars, y rompe con JSONDecodeError si Vercel manda un
    # CSV plano en vez de un array JSON. Se parsea abajo en `cors_origins`.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173,http://localhost:3000,https://cs-comunicacion.vercel.app"
    # En Vercel el filesystem del proyecto es de solo lectura; solo /tmp es
    # escribible (y efímero: se pierde entre invocaciones/cold starts). Si
    # no se define UPLOAD_DIR por env var, cae a /tmp/uploads en Vercel para
    # no romper con "Read-only file system" al subir un archivo.
    UPLOAD_DIR: str = "/tmp/uploads" if os.getenv("VERCEL") else "uploads"

    # Valores optativos: los despliegues existentes conservan public y su arranque.
    APP_ENV: Literal["production", "development", "test"] = "production"
    DATABASE_SCHEMA: str = "public"
    AUTO_CREATE_TABLES: bool = True
    TEST_DATABASE_PROJECT_REF: str = ""
    TEST_SEED_PASSWORD: SecretStr = SecretStr("")

    @field_validator("DATABASE_SCHEMA")
    @classmethod
    def safe_schema(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value) or value.startswith("pg_"):
            raise ValueError("DATABASE_SCHEMA no es un identificador permitido.")
        return value

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> List[str]:
        """Lista de orígenes permitidos. Acepta CSV o un JSON array."""
        s = self.CORS_ORIGINS.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                return json.loads(s)
            except Exception:
                pass
        return [origin.strip() for origin in s.split(",") if origin.strip()]


settings = Settings()
