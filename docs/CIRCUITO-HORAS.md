# Circuito de horas · desarrollo

Contrato actual: `GET /api/v1/practicas/capacidades` devuelve `versionHoras: 2`. Añade motivos, revisión e historial de cambios. El incremento 9 usaba versión 1 y tablas existentes; el 13 requiere la migración aditiva indicada abajo, sin reinicializar datos.

## Contratos

- `GET /practicas` y `GET /practicas/{id}/horas`: alumno propietario, docente del aula, supervisor vinculado mediante `Supervisor.user_id` o administración. Historial y reporte usan el mismo alcance.
- `POST /practicas/{id}/horas`: solo alumno propietario, práctica abierta; 1–24 horas enteras, descripción no vacía hasta 2000 caracteres y fecha válida no futura según Lima. Las fechas civiles se guardan al mediodía de Lima. No se presupone un mínimo académico diario.
- El POST admite `solicitudId` (16–80 caracteres alfanuméricos/guiones). La app lo conserva al reconciliar una respuesta incierta. La clave determina el ID del registro; repetir la misma solicitud devuelve el registro existente (201), mientras que reutilizarla con datos distintos da 409. Los clientes anteriores que no envían clave conservan el contrato de creación habitual.
- `PUT /empresa/horas/{id}` con `estadoValidacion: VALIDADO | RECHAZADO`, `revision` entera y `observacion` (obligatoria al rechazar, hasta 2000 caracteres). Solo supervisor vinculado, registro pendiente y práctica abierta. Incrementa la revisión; repetir revisión original, decisión y observación devuelve el resultado existente sin escribir. Otra revisión/decisión da 409.
- `PUT /practicas/{practicaId}/horas/{id}`: alumno propietario, registro rechazado y práctica abierta. Recibe fecha, horas, descripción y revisión. Debe cambiar al menos un dato; conserva el ID, incrementa revisión y devuelve PENDIENTE. Repetir exactamente el reenvío confirmado es inocuo; los datos antiguos dan 409.
- `GET /practicas/{practicaId}/horas/{id}/historial`: mismo alcance que la práctica. Orden por revisión; responsable/fecha, acción e instantáneas antes/después. Incluye la observación original después de corregir. Los registros anteriores a la migración no tienen acciones históricas inventadas.

Los registros devuelven `revision` y `observacion`. La versión 1 de revisión sin revisión explícita ahora recibe 422; la app nueva bloquea su uso contra servidores de versión 1 para no perder las observaciones. Consulta y registro siguen disponibles en versión 1.

Las escrituras bloquean primero la práctica y después el registro cuando corresponde. Se recalcula el acumulado mediante la suma de registros `VALIDADO`, dentro de la misma transacción; crear pendientes y rechazar no aumenta el avance. Las respuestas de prácticas calculan las horas validadas desde los registros, incluso si un acumulado antiguo era incorrecto. No se ha ejecutado una corrección masiva de datos anteriores.

El cierre solo permite docente responsable/administración, bloquea la práctica y recalcula horas validadas antes de comprobar el mínimo. El checklist académico completo del cierre sigue pendiente; no se declara resuelto por esta corrección.

## Migración del entorno autorizado

Antes de iniciar la API actualizada sobre una base de pruebas existente:

```powershell
cd C:\proyectos\appSSP-backend
.\.venv\Scripts\python.exe -m app.db.migrate_hours_test
```

El script exige development/test, proyecto esperado y esquema ssp_test. En una transacción añade revisión (0 para existentes), observación vacía e historial con unicidad por registro/revisión. El índice compuesto cubre consultas por registro; el autor tiene índice propio. Activa RLS, revoca permisos de PUBLIC/anon/authenticated y verifica aislamiento. Es aditivo e idempotente, con espera de bloqueo limitada. Un fallo revierte los cambios. No modifica public/auth/storage, ni carga semilla.

Cada registro, revisión y corrección crea un evento de historial y un evento administrativo en la misma transacción. Los reintentos no generan eventos. La aplicación no ofrece edición/eliminación del historial. El propietario PostgreSQL sigue siendo el rol de ejecución del entorno de desarrollo; separar rol de migración/ejecución y preparar migraciones de producción sigue pendiente. No usar este script como despliegue de producción.

## Verificación

`python -m unittest discover -s tests -p test_hours_flow.py`: ocho pruebas aisladas de validación, permisos, repetición, rechazo, acumulado, cierre, corrección/historial y revisiones obsoletas. No conectan con Supabase.

Migración comprobada en Supabase autorizado. Chromium y API recorren registro → rechazo concurrente con un solo evento → corrección/reenvío y repetición → revisión antigua 409 → validación nueva. Historial de cuatro cambios y solo tres horas corregidas añadidas al acumulado. Evidencias locales ignoradas en el incremento 13 de la app. Borradores persistentes y política académica definitiva siguen pendientes. Integración a main y publicación de producción requieren autorización concreta.
