# Circuito de horas · desarrollo

Implementado sobre las tablas existentes, sin migración ni reinicialización. La app comprueba primero `GET /api/v1/practicas/capacidades` (`versionHoras: 1`) para no habilitar escrituras contra servidores anteriores.

## Contratos

- `GET /practicas` y `GET /practicas/{id}/horas`: alumno propietario, docente del aula, supervisor vinculado mediante `Supervisor.user_id` o administración. Historial y reporte usan el mismo alcance.
- `POST /practicas/{id}/horas`: solo alumno propietario, práctica abierta; 1–24 horas enteras, descripción no vacía hasta 2000 caracteres y fecha válida no futura según Lima. Las fechas civiles se guardan al mediodía de Lima. No se presupone un mínimo académico diario.
- El POST admite `solicitudId` (16–80 caracteres alfanuméricos/guiones). La app lo conserva al reconciliar una respuesta incierta. La clave determina el ID del registro; repetir la misma solicitud devuelve el registro existente (201), mientras que reutilizarla con datos distintos da 409. Los clientes anteriores que no envían clave conservan el contrato de creación habitual.
- `PUT /empresa/horas/{id}` con `estadoValidacion: VALIDADO | RECHAZADO`: solo supervisor vinculado a la empresa de la práctica. Solo cambia un registro pendiente y una práctica abierta. Repetir la misma decisión es inocuo; intentar cambiar una decisión final da 409.

Las escrituras bloquean primero la práctica y después el registro cuando corresponde. Se recalcula el acumulado mediante la suma de registros `VALIDADO`, dentro de la misma transacción; crear pendientes y rechazar no aumenta el avance. Las respuestas de prácticas calculan las horas validadas desde los registros, incluso si un acumulado antiguo era incorrecto. No se ha ejecutado una corrección masiva de datos anteriores.

El cierre solo permite docente responsable/administración, bloquea la práctica y recalcula horas validadas antes de comprobar el mínimo. El checklist académico completo del cierre sigue pendiente; no se declara resuelto por esta corrección.

## Verificación

`python -m unittest discover -s tests -p test_hours_flow.py`: cinco pruebas aisladas de validación, pertenencia, repetición, rechazo, acumulado y cierre. No conectan con Supabase. La verificación PostgreSQL y navegador se registra en el incremento 9 de la app y en evidencias locales ignoradas.

Pendientes: auditoría persistente de quién/cuándo revisó, observaciones de rechazo, corrección/reenvío de registros y política académica definitiva. No se añadieron columnas para simular estas capacidades. Rama de desarrollo; producción no recibe estos cambios hasta una integración y publicación autorizadas.
