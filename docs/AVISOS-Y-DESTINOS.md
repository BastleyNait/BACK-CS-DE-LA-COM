# Avisos con destino · Incremento 22

La bandeja paginada `GET /api/v1/notificaciones/bandeja` acepta `estado=todos|pendientes|leidos`, `limite=1..50` (predeterminado 20) y `cursor`. Devuelve `items`, `total` del filtro, `sinLeer` global de la cuenta y `siguiente`. Orden estable por fecha/ID descendentes; no descarga todo el historial. `GET /api/v1/notificaciones/{id}` devuelve el detalle propio. GET no cambia la lectura. Se conserva la lista anterior sin paginar por compatibilidad.

Publicar o editar una tarea genera avisos para los alumnos matriculados. Revisar horas genera un aviso para su practicante. Se guardan en la transacción del evento y se respetan sus controles de concurrencia e idempotencia; no se generan al repetir una solicitud confirmada. Una transacción fallida no deja un aviso huérfano. No hay correos, push ni proceso programado de vencimientos.

`destino` es JSONB nullable con forma TAREA (`aulaId`, `tareaId`) o ACTIVIDAD (`practicaId`, `registroId`); no admite enlaces externos. Los avisos antiguos o con destino incompatible siguen siendo informativos. No se reconstruye ni envía el historial anterior. Los detalles académicos vuelven a comprobar permisos al abrirse; el aviso no concede acceso.

Migración aplicada una vez en la base de pruebas autorizada:

```powershell
.\.venv\Scripts\python.exe -m app.db.migrate_notices_test
```

Valida proyecto/esquema/entorno, añade la columna nullable, los valores `TAREA_ACTUALIZADA` y `REVISION_HORAS` al enum y el índice `(user_id, fecha DESC, id DESC)`. Mantiene RLS y revoca acceso de PUBLIC/anon/authenticated. Aditiva, sin semillas, sin datos académicos y sin aplicar a producción.

Seis pruebas nuevas `test_notification_flow.py` y regresiones afectadas `test_task_flow.py` (4) y `test_hours_flow.py` (8), correctas con SQLite en memoria. La app añade contratos de cliente y revisión de interfaz con recursos locales reales y escrituras de lectura simuladas. No hay publicación ni fusión con main.
