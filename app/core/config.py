import json
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ssp_db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # OJO: se declara como `str`, no `List[str]`, a propósito.
    # pydantic-settings intenta json.loads() sobre los campos tipo lista/dict al
    # leerlos de variables de entorno (antes de cualquier validator), así que un
    # valor CSV como "https://a.com,https://b.com" rompería el arranque con
    # JSONDecodeError. Como str se lee literal y lo parseamos en `cors_origins`.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173"
    UPLOAD_DIR: str = "uploads"

    @property
    def cors_origins(self) -> List[str]:
        """Lista de orígenes permitidos. Acepta CSV o un JSON array."""
        s = self.CORS_ORIGINS.strip()
        if not s:
            return []
        if s.startswith("["):
            return json.loads(s)
        return [origin.strip() for origin in s.split(",") if origin.strip()]


settings = Settings()
