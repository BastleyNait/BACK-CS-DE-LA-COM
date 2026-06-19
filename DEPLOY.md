# Desplegar el SSP Backend en Vercel

FastAPI corre en Vercel como **Serverless Functions** (runtime `@vercel/python`).
Este repo ya está configurado para ello:

- `api/index.py` → entrypoint ASGI que Vercel detecta.
- `vercel.json` → reescribe todas las rutas hacia FastAPI.
- `app/core/config.py` → lee `CORS_ORIGINS` como texto separado por comas.
- `app/db/session.py` → usa `NullPool` (apto para serverless).

Faltan **2 pasos que solo tú puedes hacer**: una base de datos en la nube y las
variables de entorno. Sigue esta guía.

---

## 1. Base de datos PostgreSQL en la nube — YA CREADA ✅

Ya existe un proyecto Supabase dedicado, con esquema y datos sembrados:

| Dato | Valor |
|------|-------|
| Proyecto | `ssp-backend` (org BOOM POS) |
| Project ref | `tyhvaplchdaruqdonivc` |
| Región | `us-east-1` |
| API URL | https://tyhvaplchdaruqdonivc.supabase.co |
| Dashboard | https://supabase.com/dashboard/project/tyhvaplchdaruqdonivc |

Las tablas `users` y `aulas` ya están creadas (espejo exacto de
`app/models/models.py`) y sembradas con los 3 usuarios y 2 aulas de prueba.
**No necesitas correr el seed.**

### Obtener el `DATABASE_URL`
Por seguridad, la contraseña de la BD no se expone por API. Sácala del dashboard:

1. Abre **Dashboard → (proyecto ssp-backend) → botón "Connect"** (arriba).
2. Elige **Transaction pooler** (puerto **6543**) y copia la cadena. Se ve así:
   ```
   postgresql://postgres.tyhvaplchdaruqdonivc:[PASSWORD]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
   ```
3. Reemplaza `[PASSWORD]` por la contraseña de la BD. Si no la tienes a mano,
   en **Settings → Database → "Reset database password"** generas una nueva.

> Usa el **pooler (6543)**, no la conexión directa (5432): en serverless la
> directa agota las conexiones.

---

## 2. (Solo si cambias el esquema en el futuro)

La BD ya está sembrada, así que puedes saltarte este paso. Si más adelante
modificas los modelos, vuelve a sembrar desde tu PC apuntando a la BD remota:

```bash
cd ssp-backend/ssp-backend
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt

set DATABASE_URL=postgresql://postgres.tyhvaplchdaruqdonivc:PASS@aws-0-us-east-1.pooler.supabase.com:6543/postgres
python -m app.db.seed
```

---

## 3. Crear el proyecto en Vercel

El frontend ya es un proyecto Vercel aparte. El backend debe ser **su propio
proyecto** (no se puede mezclar Vite estático + Python en el mismo).

1. En Vercel → **Add New → Project** → importa este repositorio.
2. **IMPORTANTE — Root Directory:** `ssp-backend/ssp-backend`
   (no la raíz del repo; ahí está el frontend).
3. Framework Preset: **Other**. Vercel detectará `requirements.txt` + `api/`.

---

## 4. Variables de entorno en Vercel

En **Project → Settings → Environment Variables** añade:

| Clave | Valor |
|-------|-------|
| `DATABASE_URL` | la cadena del pooler de Supabase (paso 1) |
| `SECRET_KEY` | genera una: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | la URL de tu frontend, ej. `https://cs-comunicacion.vercel.app` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` (opcional) |

Luego haz **Deploy** (o redeploy si ya estaba).

---

## 5. Conectar el frontend

En el frontend, apunta la `BASE_URL` del `apiClient.ts` al dominio del backend:

```ts
export const BASE_URL = "https://<tu-backend>.vercel.app";
```

Y asegúrate de que esa URL del frontend esté en `CORS_ORIGINS` (paso 4).

---

## 6. Verificar

- `https://<tu-backend>.vercel.app/` → `{"status":"ok","app":"SSP Backend"}`
- `https://<tu-backend>.vercel.app/docs` → Swagger UI.
- Prueba el login con `admin@unsa.edu.pe` / `admin123`.

---

## Notas / limitaciones de serverless

- **Cold starts:** la primera petición tras inactividad tarda 1–3 s (incluye el
  hash bcrypt). Es normal en el plan Hobby.
- **`/recover`** solo responde un mensaje; no envía email real todavía.
- Si cambias modelos, vuelve a correr el seed/migración contra la BD remota.
- `uvicorn` y `alembic` están en `requirements.txt` solo para uso local; Vercel
  los instala pero no los necesita en runtime.
