# Backend de prueba · Supabase

Repositorio paralelo: `C:\proyectos\appSSP-backend`. Rama de desarrollo separada de `main`. La app mantiene la arquitectura Expo → FastAPI → PostgreSQL; las cuentas y JWT siguen siendo del backend existente. No se necesita `@supabase/supabase-js` en el móvil para esta conexión.

## Preparación en PowerShell de Windows

```powershell
cd C:\proyectos\appSSP-backend
.\scripts\preparar-pruebas.ps1
```

El script crea `.venv`, instala `requirements.txt` y prepara `.env` si no existe. Genera SECRET_KEY y TEST_SEED_PASSWORD locales; no los imprime ni reemplaza un `.env` existente.

En Supabase, abrir **Connect → Session pooler**, puerto **5432**. Copiar la cadena PostgreSQL completa a `DATABASE_URL` en `.env`, sustituyendo la contraseña y codificando caracteres reservados si corresponde. Completar `TEST_DATABASE_PROJECT_REF` con la referencia del proyecto vacío de pruebas. Las claves publicables `sb_publishable_...` no son contraseñas de PostgreSQL.

```dotenv
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:5432/postgres
TEST_DATABASE_PROJECT_REF=PROJECT_REF
DATABASE_SCHEMA=ssp_test
APP_ENV=development
AUTO_CREATE_TABLES=false
```

Tomar host, usuario y contraseña del panel; no adivinarlos. No guardar credenciales en Git. Para inicializar y arrancar:

```powershell
.\scripts\iniciar-pruebas.ps1 -Inicializar
```

Arranques posteriores: `scripts\iniciar-pruebas.ps1`. Swagger: `http://localhost:8000/docs`. Comprobación sin modificar datos:

```powershell
.\.venv\Scripts\python.exe -m app.db.bootstrap_test --check
```

## Aislamiento y datos ficticios

El inicializador exige entorno development/test, esquema `ssp_test`, proyecto coincidente en host/usuario y puerto 5432. Fuerza SSL y timeout de conexión. Crea solo ese esquema y las tablas del backend, activa RLS y retira acceso de PUBLIC/anon/authenticated. El esquema no debe añadirse a los esquemas expuestos por la Data API de Supabase. No modifica `public`, `auth` ni `storage`.

La semilla agrega seis cuentas (`admin`, `profesor`, `alumno`, `supervisor`, `profesor2`, `alumno2`), con correos como `alumno.prueba@unsa.edu.pe`. Usan la contraseña local TEST_SEED_PASSWORD. Incluye dos aulas con distintos propietarios, dos prácticas activas, centros ficticios, un supervisor vinculado, tareas, entregas y avisos. No carga archivos, jornadas ni calificaciones reales. Reejecutarla conserva los registros existentes y rechaza usuarios ajenos a la semilla.

`create_all` prepara esta base vacía; no sustituye migraciones Alembic para futuros cambios de estructura. La conexión actual usa el propietario PostgreSQL durante este entorno de desarrollo; antes de un piloto se debe separar el rol de migraciones del rol de ejecución con privilegios mínimos.

## Actualizar una base de pruebas existente

El incremento 13 añade revisiones, observaciones e historial de horas. Ejecutar una vez antes de usar la API actualizada:

```powershell
.\.venv\Scripts\python.exe -m app.db.migrate_hours_test
```

Es aditivo e idempotente, limitado al proyecto y esquema autorizados; no vuelve a cargar la semilla. Ver [CIRCUITO-HORAS.md](CIRCUITO-HORAS.md). `create_all` no añade columnas a tablas existentes.

## Conectar la app

Detener el Expo anterior en 5173. En otro PowerShell:

```powershell
cd C:\proyectos\appSSP
npm run web
```

`npm run web` y su alias `npm run web:pruebas` comprueban `/dev/ready`, rechazan otro servidor en 5173 y configuran EXPO_PUBLIC_API_URL local solo para ese proceso. Para abrir deliberadamente la API configurada en `.env.local`/el entorno (con el backend público anterior como valor de respaldo), detener el Expo anterior y usar `npm run web:configurado`. El login muestra el entorno elegido. Estos comandos usan localhost; acceso desde un teléfono requiere configurar direcciones de red por separado.

Las tablas se consultan en el esquema **`ssp_test`** del proyecto de pruebas, no en `public`. Las cuentas de ingreso están en **`ssp_test.users`**, no en Supabase Auth. Para comprobarlo sin modificar datos, ejecutar en el editor SQL del proyecto correcto:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'ssp_test' AND table_type = 'BASE TABLE'
ORDER BY table_name;
SELECT count(*) AS cuentas_ssp FROM ssp_test.users;
```

La comprobación del 17 de octubre de 2026 encontró 21 tablas con RLS, 7 cuentas ficticias y cero tablas en `public`. El script de la app `npm run test:login:real` verifica en Chromium un rechazo 401, un ingreso 200 y el panel del alumno contra la API local real, sin respuestas simuladas ni nuevas escrituras académicas. Requiere Playwright y la contraseña local existente; no publica credenciales.

## Verificación y Git

Ejecutar únicamente las comprobaciones afectadas:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

El caso de seguridad rechaza producción, otro proyecto, `public`, URL vacía y el pooler de transacciones. La conexión, creación y recorrido real se comprueban al completar DATABASE_URL. `.env`, `.venv`, `.local`, cachés y archivos subidos quedan fuera de Git. Subir cada incremento a una rama de desarrollo; integrar a `main` y desplegar producción requieren una decisión separada y variables del entorno correcto.

Fuentes: [conexiones PostgreSQL de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [claves de API](https://supabase.com/docs/guides/api/api-keys), [search_path en SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#setting-alternate-search-paths-on-connect).
