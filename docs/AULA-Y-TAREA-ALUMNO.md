# Aula y detalle de tarea del alumno · Incremento 23

Nuevas lecturas, bajo `/api/v1/alumno/aulas/{aula_id}`:

- `GET /tareas/pagina`: estados `pendientes` (predeterminado), `entregadas`, `calificadas` o `todas`; `limite` de 1 a 50, predeterminado 20, y cursor. Devuelve filas resumidas, cantidad del filtro, resumen global propio y cursor siguiente.
- `GET /tareas/{tarea_id}`: tarea individual y entrega propia, nombre del aula, `entregaHabilitada` y `bloqueoEntrega`.

La página ordena por plazo ascendente, fechas nulas al final, e identificador ascendente como desempate. El cursor conserva plazo/ID y consulta `limite + 1` filas. Usa una unión con la entrega del alumno; no consulta una entrega por cada fila. Los contadores y el promedio se agregan sobre todas sus tareas del aula, independientemente del filtro o la página. No devuelve descripciones extensas ni versiones en las filas.

El detalle calcula las revisiones con MAX; no carga el contenido del historial. Una tarea calificada, un plazo terminado, un aula concluida o una práctica cerrada impiden ofrecer el formulario. Es una lectura de disponibilidad; las escrituras existentes siguen comprobando sus permisos y condiciones al confirmar.

Ambas rutas exigen ALUMNO y matrícula en el aula. La entrega de otra cuenta no interviene en sus notas ni contadores. La lista anterior permanece compatible. No hay cambios de esquema, migraciones ni semillas, ni fusión con main o publicación.

Verificación: seis pruebas `test_student_tasks.py` sobre SQLite en memoria, correctas. Incluyen páginas 20/20/5 con plazos repetidos y nulos, filtros, totales, nota cero, aislamiento, matrícula retirada, cursor inválido y bloqueos. La app comprueba además lecturas reales locales y recorridos con envíos simulados, sin escrituras académicas reales.
