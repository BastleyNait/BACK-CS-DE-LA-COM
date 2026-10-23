# Recorrido de práctica del alumno

Incremento 25: consulta resumida del expediente para la interfaz del alumno. La entrega del 23 de octubre permanece separada.

`GET /api/v1/expedientes/{practica_id}/resumen` exige ALUMNO y reutiliza `require_practice` para consultar únicamente la práctica propia. Otros roles reciben 403; una práctica ajena o inexistente devuelve 404. La consulta completa sigue disponible para el circuito previo de gestión y PDF.

El resumen devuelve práctica, centro, supervisor, criterios (motivo, responsable, fecha y nota mínima), evaluación y vigencia, checklist y estado/copia de cierre. No incluye las listas de horas, tareas y metas, la selección de identificadores de requisitos ni una revisión de autorización de cierre.

`build(..., compact=True)` mantiene los mismos cálculos de requisitos. En una práctica abierta suma las horas validadas en SQL, sin materializar registros individuales, y restringe tareas/entregas/metas a las exigidas en la configuración. Selecciona solo las columnas necesarias; evita descripciones extensas y textos de entregas. Para un cierre ya conservado aplica la proyección al JSON congelado, sin recalcularlo desde los datos actuales. Las llamadas existentes a `build` conservan su contenido y la revisión SHA-256 del cierre.

No se modifican tablas, tipos, políticas, índices ni datos reales. Las pruebas nuevas usan SQLite en memoria: equivalencia de requisitos y totales, agregado sin historial, selección faltante, permisos y copia congelada. Se ejecutan también las ocho pruebas existentes del expediente porque el constructor es compartido.

El cliente alumno muestra resumen, requisitos y accesos; el docente/supervisor/administración conservan la pantalla de gestión anterior. La API no cambia los criterios institucionales ni autoriza al alumno a cerrar, evaluar o modificar requisitos. Publicación y APK de presentación siguen en sus versiones anteriores.
