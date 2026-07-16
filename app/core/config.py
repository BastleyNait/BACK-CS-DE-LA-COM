from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ssp_db"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:4173"]
    UPLOAD_DIR: str = "uploads"

    class Config:
        env_file = ".env"


settings = Settings()
