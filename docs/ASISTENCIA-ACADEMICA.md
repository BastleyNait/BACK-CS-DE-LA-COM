# Asistencia académica · revisión y padrón

El GET existente devuelve `versionAsistencia: 1`, `estadoRegistro`, `revision` y `registrado` por estudiante. Se usan las tablas existentes, sin migración ni reinicialización.

- `PROPUESTO`: no hay registros del día; los presentes son valores propuestos.
- `GUARDADO`: cada alumno del padrón actual tiene exactamente un registro.
- `PARCIAL`: hay registros, pero faltan alumnos actuales o hay duplicados entre ellos.

El padrón se obtiene de la matrícula y de usuarios ALUMNO; se deduplican matrículas históricas repetidas. Los registros de alumnos retirados se conservan y no impiden reconocer como guardado el padrón actual. No se reconstruye un padrón histórico por fecha.

## Guardado

`POST /api/v1/profesor/aulas/{aula_id}/asistencia` requiere `fecha`, `items` y `revision` de la consulta. La lista debe coincidir exactamente con el padrón actual: sin faltantes, IDs ajenos, duplicados ni lista vacía. `presente` es booleano estricto. Exige aula activa, docente responsable/ADMIN y fecha civil válida no futura según Lima.

El aula se bloquea antes de comprobar el padrón y la revisión. Una lista obsoleta diferente del estado actual da 409 sin sobrescribir. Repetir un resultado ya guardado devuelve el registro actual sin otra escritura ni auditoría. Las operaciones administrativas de matrícula/retiro, asignación de docente y cambio de estado usan el mismo bloqueo de aula.

Se reemplazan únicamente las filas del día de alumnos del padrón actual; los retirados conservan su historial. Los IDs deterministas por aula/fecha/alumno y la normalización evitan filas duplicadas. Por compatibilidad, la fecha académica sigue codificada a las 00:00 UTC del día civil indicado; no es la hora de una jornada laboral.

Cada cambio se guarda con una entrada `ASISTENCIA_ACADEMICA` en la tabla existente `auditoria`, dentro de la misma transacción: actor, fecha, aula/día, revisión anterior, padrón y valores anteriores/nuevos, con referencia a filas conservadas fuera del padrón. Acceso administrativo mediante `/api/v1/admin/auditoria`. Los registros anteriores no reciben una autoría inventada.

## Compatibilidad y verificación

La app consulta servidores anteriores, pero solo permite guardar cuando reconoce la versión y recibe una revisión válida. Los clientes antiguos sin revisión reciben 422 al escribir en este backend actualizado.

`python -m unittest discover -s tests -p test_attendance_flow.py`: seis pruebas aisladas de propuesta/guardado, repetición y auditoría, padrón, conflicto, fechas/permisos, historial retirado y normalización de filas antiguas. El recorrido real está documentado en el incremento 11 de la app.

Pendiente: padrón histórico por sesión, pantalla dedicada de auditoría y procedimientos académicos de corrección. Rama de desarrollo; producción no se ha desplegado.
