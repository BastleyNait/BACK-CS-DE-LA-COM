# SSP Backend — Despliegue en Vercel

## Estado: ✅ DESPLEGADO Y FUNCIONANDO

- **API:** https://back-cs-de-la-com.vercel.app
- **Docs (Swagger):** https://back-cs-de-la-com.vercel.app/docs
- **Proyecto Vercel:** `back-cs-de-la-com` (team CS DE LA COMUNICACION)
- **Repo:** https://github.com/BastleyNait/BACK-CS-DE-LA-COM

## Base de datos

- **Proyecto Supabase:** CS-DE-COMUNICACIONs (`pddyxgcvczomdemquvum`, región sa-east-1)
- Tablas `users` y `aulas` (espejo de `app/models/models.py`), con los usuarios y aulas de prueba sembrados.
- El backend se conecta por el **pooler en modo Transaction** (puerto 6543, host `aws-1-sa-east-1`), apto para serverless.

## Variables de entorno (configuradas en Vercel → Settings → Environment Variables)

| Clave | Descripción |
|-------|-------------|
| `DATABASE_URL` | `postgresql://postgres.pddyxgcvczomdemquvum:<password>@aws-1-sa-east-1.pooler.supabase.com:6543/postgres` |
| `SECRET_KEY` | clave para firmar los JWT |
| `CORS_ORIGINS` | orígenes permitidos (CSV), incluye `https://cs-comunicacion.vercel.app` |

> Los valores reales están en Vercel (cifrados), no en este repo.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login → JWT + datos del usuario |
| POST | `/api/v1/auth/register` | Registrar cuenta |
| POST | `/api/v1/auth/recover` | Solicitar reset de contraseña (aún sin envío de email) |
| GET | `/api/v1/aulas` | Listar aulas (RBAC por rol) |
| POST | `/api/v1/aulas` | Crear aula (solo ADMIN/PROFESOR) |

## Usuarios de prueba

| Rol | Correo | Contraseña |
|-----|--------|------------|
| Admin | admin@unsa.edu.pe | admin123 |
| Profesor | profesor@unsa.edu.pe | profesor123 |
| Alumno | alumno@unsa.edu.pe | alumno123 |

## Conectar el frontend

En el frontend, apunta la `BASE_URL` del `apiClient.ts` al backend:

```ts
export const BASE_URL = "https://back-cs-de-la-com.vercel.app";
```

Y asegúrate de que el dominio del frontend esté en `CORS_ORIGINS` (variable en Vercel).

## Re-desplegar

Desde `ssp-backend/ssp-backend/`:

```bash
vercel --prod
```

(O conecta el repo de GitHub a Vercel para auto-deploy en cada push.)

## Arquitectura para Vercel (notas)

- `api/index.py` → entrypoint ASGI; Vercel detecta FastAPI y sirve `app/main.py`.
- `app/core/config.py` → `CORS_ORIGINS` se lee como **str** (no `List`), porque
  pydantic-settings hace `json.loads()` sobre los campos lista de las env vars y
  rompería con un CSV. Se parsea en la property `cors_origins`.
- `app/db/session.py` → `NullPool` (el pooler de Supabase gestiona las conexiones).
