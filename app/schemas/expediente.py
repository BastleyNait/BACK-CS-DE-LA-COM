from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequisitosRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(ge=0, strict=True)
    tareas: list[str] = Field(max_length=200)
    metas: list[str] = Field(max_length=200)
    notaMinima: int | None = Field(default=None, ge=0, le=20, strict=True)
    motivo: str = Field(min_length=5, max_length=2000)

    @field_validator("tareas", "metas")
    @classmethod
    def distinct(cls, values):
        if len(set(values)) != len(values) or any(not v.strip() or len(v) > 200 for v in values):
            raise ValueError("Selecciona identificadores distintos y válidos.")
        return sorted(values)


class EvaluacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(ge=0, strict=True)
    desempeno: str = Field(min_length=10, max_length=4000)
    fortalezas: str = Field(min_length=5, max_length=2000)
    mejoras: str = Field(min_length=5, max_length=2000)
    conclusion: Literal["FAVORABLE", "REQUIERE_MEJORAS"]
    conformidad: Literal[True]

    @field_validator("conformidad", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirma expresamente la evaluación.")
        return value


class CerrarExpedienteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    motivo: str = Field(min_length=5, max_length=2000)
