# Administración y seguimiento · incremento 15

Sin migración. /admin/capacidades devuelve versionAdministracion=1 y exige ADMIN. /profesor/seguimiento/capacidades devuelve versionSeguimiento=1 y exige PROFESOR/ADMIN.

## Contratos

- GET /admin/usuarios; PUT /admin/usuarios/{id}/rol con role y anterior. Prohíbe cambiar la propia cuenta, exige estado anterior salvo repetición del resultado y rechaza cuentas con aula, inscripción, práctica, empresa o vínculo de supervisor. Serializa cambios de roles mediante advisory lock transaccional por esquema; revalida al actor después de esperar. Los destinos se bloquean para coordinar con asignación y matrícula.
- GET/POST /admin/aulas. Alta exige docente responsable, código único, campos limitados y solicitudId opcional. Repetición idéntica devuelve la misma aula (201), otros datos/códigos conflictivos dan 409. POST /aulas conserva alta docente propia; rechaza supervisor y asignaciones a usuarios sin rol docente.
- PUT /admin/aulas/{id}/profesor y /estado exigen anterior. Repetir resultado no escribe, valor obsoleto distinto da 409.
- GET /admin/aulas/{id}/matriculas incluye revision del padrón/estado. PUT /admin/aulas/{id}/matriculas/{alumnoId} recibe inscrito booleano estricto y revision. Bloquea aula antes de alumno, valida rol, estado y padrón. Repetir resultado es inocuo. POST/DELETE anteriores conservan compatibilidad bajo bloqueo e idempotencia; no ofrecen la revisión optimista del PUT nuevo.
- Retirar borra la inscripción actual (incluido su avance) y conserva las tablas independientes de entregas, asistencia y prácticas. No borra usuarios ni expedientes históricos. Aulas concluidas requieren reactivación antes de cambiar matrículas.
- GET /admin/reportes calcula horas promedio desde registros VALIDADO y matrículas desde inscripciones distintas.
- GET /profesor/aulas/{aulaId}/practicantes/{alumnoId}/seguimiento exige matrícula y propiedad docente/ADMIN. Usa horas VALIDADO y no datos acumulados antiguos.
- POST /auth/register solo admite ALUMNO. Rechaza roles privilegiados antes de crear una cuenta. El correo sigue sin verificación institucional.

## Lecturas paginadas

Incremento 33. Seis lecturas solo ADMIN, de 1–40 elementos (la app pide 20), con cursor ligado a usuario, filtro y búsqueda; reutilizar el cursor en otra consulta devuelve 422.

- GET /admin/usuarios/pagina?rol=&q=&limite=&cursor= ordena por apellidos y nombres, busca en nombres, apellidos y correo, y devuelve totalDocentes global.
- GET /admin/aulas/pagina?estado=&q=&limite=&cursor= ordena por nombre, busca en nombre, código, periodo y docente, e incluye descripción, docente e inscritos; devuelve aulasActivas global.
- GET /admin/aulas/{id} devuelve la ficha exacta con descripción y matrículas reales.
- GET /admin/aulas/{id}/matriculas/pagina?estado=&q=&limite=&cursor= pagina el padrón con revision, matriculados y total del filtro.
- GET /admin/reportes/pagina?estado=&q=&limite=&cursor= calcula el resumen global en SQL (horas promedio desde VALIDADO) y añade por fila inscritos, promedioNotas y asistenciaPct; incluye aulaId y aulaNombre.
- GET /admin/auditoria/pagina?categoria=&q=&limite=&cursor= pagina por fecha descendente y resuelve aulaNombre y estudiantes en el servidor; la búsqueda cubre responsable, acción y detalle, no los nombres resueltos.

Las rutas completas anteriores siguen disponibles para escrituras y compatibilidad del APK fijado; las pantallas nuevas no las consultan.

Cada modificación efectiva genera Auditoria transaccional; no por repeticiones ni rechazos. No cambiar roles de cuentas de prueba vinculadas para probar esta función; usar una cuenta ficticia sin asignaciones y restaurar su rol.

## Comprobación

python -m unittest discover -s tests -p test_administration_flow.py (9 casos); test_attendance_flow.py (6 casos del bloqueo compartido). Incluye pertenencia, dependencias de rol, registro público, alta idempotente, conflictos, padrón, cierre, horas validadas y lecturas paginadas con totales globales, filtros y cursores por scope.

La app añade test:administracion, exportación web e integración ficticia con Supabase. No se fusiona main ni se publica producción.
