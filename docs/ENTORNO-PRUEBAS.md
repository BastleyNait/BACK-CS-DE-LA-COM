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

## Conectar la app

Detener el Expo anterior en 5173. En otro PowerShell:

```powershell
cd C:\proyectos\appSSP
npm run web:pruebas
```

El comando comprueba `/dev/ready` y configura EXPO_PUBLIC_API_URL solo para ese proceso. No cambia la URL predeterminada ni guarda credenciales en Expo. `npm run web` conserva el arranque habitual. Estos comandos usan localhost; acceso desde un teléfono requiere configurar direcciones de red por separado.

## Verificación y Git

Ejecutar únicamente las comprobaciones afectadas:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

El caso de seguridad rechaza producción, otro proyecto, `public`, URL vacía y el pooler de transacciones. La conexión, creación y recorrido real se comprueban al completar DATABASE_URL. `.env`, `.venv`, `.local`, cachés y archivos subidos quedan fuera de Git. Subir cada incremento a una rama de desarrollo; integrar a `main` y desplegar producción requieren una decisión separada y variables del entorno correcto.

Fuentes: [conexiones PostgreSQL de Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [claves de API](https://supabase.com/docs/guides/api/api-keys), [search_path en SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#setting-alternate-search-paths-on-connect).
