# Publicación y entrega escrita · desarrollo

Se usan las tablas existentes `tareas` y `entregas`; no hay migración ni reinicialización.

- `GET /api/v1/tareas/capacidades`: autenticado, responde `versionTareas: 1` y `entregaTexto: true`. La app comprueba este contrato antes de ofrecer los formularios nuevos.
- `GET/POST /api/v1/profesor/aulas/{aula_id}/tareas`: docente responsable o ADMIN. El POST recibe título (1–200 caracteres), instrucciones (1–6000), fechaLimite opcional con zona horaria y solicitudId obligatorio (16–80 caracteres alfanuméricos/guiones). Requiere aula activa y plazo futuro cuando se especifica. Repetir la misma solicitud devuelve la tarea existente (201); cambiar su contenido da 409. Se bloquea el aula antes de comprobar/crear.
- `POST /api/v1/alumno/aulas/{aula_id}/tareas/{tarea_id}/entregas`: alumno matriculado, tarea de esa aula y aula activa. Requiere texto o un archivo válido. La app ofrece respuesta escrita y comentario opcional; no ofrece adjuntos todavía.

La entrega bloquea la tarea y comprueba si el alumno ya entregó. Repetir el contenido guardado devuelve la misma entrega (201), incluso si el plazo terminó después del primer envío; contenido distinto da 409. El ID determinista de entrega refuerza la unicidad sin agregar columnas. La fecha límite se comprueba con reloj del servidor. Este flujo bloquea nuevas entregas fuera de plazo; las excepciones y reemplazos requieren una política académica y desarrollo posteriores.

Si se envía archivoId desde otro cliente, su propietario debe ser el alumno y su aula debe coincidir con la tarea. Esto no implementa almacenamiento persistente ni certifica existencia física del archivo.

Verificación: `python -m unittest discover -s tests -p test_task_flow.py` (cuatro pruebas aisladas). Cubren roles/pertenencia, repetición, contenido distinto, aula concluida, plazo, datos vacíos y archivos ajenos. Evidencia PostgreSQL/navegador en el incremento 10 de la app y archivos locales ignorados.

Pendientes: edición de tareas, reemplazos y entregas tardías autorizadas, archivos persistentes y avisos de nuevas tareas. Solo rama de desarrollo; no se ha desplegado producción.
