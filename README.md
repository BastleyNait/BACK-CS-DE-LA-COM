# SSP Backend — FastAPI + PostgreSQL

Backend del **Sistema de Seguimiento de Practicantes (SSP)** que reemplaza la
capa mock del frontend React (HU-1 a HU-4).

## Stack

- **FastAPI** — framework web
- **SQLAlchemy 2** — ORM
- **PostgreSQL** — base de datos
- **passlib + bcrypt** — hashing de contraseñas
- **python-jose** — JWT reales

## Endpoints implementados

| Método | Ruta                     | HU    | Descripción                        |
|--------|--------------------------|-------|------------------------------------|
| POST   | `/api/v1/auth/login`     | HU-1  | Login → JWT + datos del usuario    |
| POST   | `/api/v1/auth/recover`   | HU-2  | Solicitar reset de contraseña      |
| POST   | `/api/v1/auth/register`  | HU-3  | Registrar nueva cuenta             |
| GET    | `/api/v1/aulas`          | HU-4  | Listar aulas (RBAC por rol)        |
| POST   | `/api/v1/aulas`          | HU-4  | Crear nueva clase/práctica         |

## Instalación y arranque

### 1. Requisitos previos
- Python 3.11+
- PostgreSQL corriendo localmente (o Docker)

### 2. Crear entorno virtual e instalar dependencias

```bash
cd ssp-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tu DATABASE_URL y una SECRET_KEY segura
```

### 4. Crear la base de datos (PostgreSQL)

```sql
CREATE DATABASE ssp_db;
```

### 5. Crear tablas e insertar datos semilla

```bash
python -m app.db.seed
```

Esto crea las tablas y agrega los mismos usuarios/aulas del `mockDb`:

| Rol      | Correo                  | Contraseña    |
|----------|-------------------------|---------------|
| Admin    | admin@unsa.edu.pe       | admin123      |
| Profesor | profesor@unsa.edu.pe    | profesor123   |
| Alumno   | alumno@unsa.edu.pe      | alumno123     |

### 6. Ejecutar el servidor

```bash
uvicorn app.main:app --reload
```

Abre `http://localhost:8000/docs` para explorar la API con Swagger UI.

## Conectar con el frontend

En el frontend, cambia la `BASE_URL` del `apiClient.ts` de mock a real:

```ts
// src/services/apiClient.ts
export const BASE_URL = "http://localhost:8000";
```

Luego reemplaza los cuerpos de `authService` y `aulaService` por llamadas
`fetch` reales a los endpoints de arriba. Los componentes no necesitan cambios.

## Estructura del proyecto

```
ssp-backend/
  app/
    main.py            ← entrypoint FastAPI + CORS
    core/
      config.py        ← settings (pydantic-settings)
      security.py      ← bcrypt + JWT
      deps.py          ← get_current_user dependency
    db/
      session.py       ← engine + SessionLocal + get_db
      seed.py          ← datos iniciales (equivale al mockDb)
    models/
      models.py        ← tablas SQLAlchemy (User, Aula)
    schemas/
      schemas.py       ← schemas Pydantic (request/response)
    routers/
      auth.py          ← /api/v1/auth/*
      aulas.py         ← /api/v1/aulas
  requirements.txt
  .env.example
```
