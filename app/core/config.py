import json
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ssp_db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:4173,http://localhost:3000,https://cs-comunicacion.vercel.app"
    UPLOAD_DIR: str = "uploads"

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
