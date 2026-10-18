# Incremento 18 · Evaluación, expediente y cierre

La app usa `/api/v1/expedientes`. El circuito reutiliza prácticas, centros, supervisores, tareas, entregas, metas y horas. Los permisos se resuelven con `require_practice`: alumno propietario, docente responsable, supervisor vinculado y administración.

- `GET /capacidades`: `versionExpediente=1`.
- `GET /{practica_id}`: requisitos calculados, evaluación, tareas, metas y horas. No escribe.
- `PUT /{practica_id}/requisitos`: docente/admin selecciona IDs de tareas del aula y metas de la práctica. Nota mínima opcional; sin valor exige nota registrada, sin inventar umbral aprobatorio. Motivo obligatorio, revisión y reintento idempotente.
- `PUT /{practica_id}/evaluacion`: exclusivamente supervisor vinculado. Desempeño, fortalezas, mejoras, conclusión y conformidad explícita. Puede actualizarse antes del cierre; revisión evita sobrescrituras. Es aprobación con cuenta SSP, no firma digital ni rúbrica institucional oficial.
- `POST /{practica_id}/cerrar`: docente/admin, revisión SHA-256 del expediente y fundamento obligatorio. Recalcula requisitos en servidor. Requiere matrícula, centro y supervisor con cuenta, requisitos confirmados, mínimo configurado de horas validadas, evaluación favorable vigente y tareas/metas seleccionadas cumplidas. La ruta antigua `/practicas/{id}/cerrar` rechaza con 409; no permite omitir el expediente.
- `GET /{practica_id}/pdf`: PDF autenticado, sin almacenamiento público ni token en URL. En curso se identifica como seguimiento; cerrado usa la copia conservada v1. El reporte JSON antiguo comparte el mismo contenido.

## Persistencia

`evaluaciones.contenido` contiene la evaluación autenticada y su revisión. `expedientes_practicas`, PK `practica_id`, conserva requisitos/revisión y la copia de cierre en JSON textual. Las operaciones toman el bloqueo de práctica antes de modificar datos dependientes. Las entregas/calificaciones vinculadas a una práctica cerrada se bloquean; también horas, metas y evaluación. El cierre repetido con la misma revisión y motivo devuelve la copia guardada sin otra auditoría.

Migración aditiva del entorno autorizado:

```powershell
.\.venv\Scripts\python.exe -m app.db.migrate_expediente_test
```

Solo `ssp_test`, valida proyecto/entorno, crea la tabla con RLS y revoca acceso PUBLIC/anon/authenticated. No inicializa ni vuelve a cargar la semilla. No aplicar a producción con este script.

El PDF se genera con ReportLab y escapa el texto antes de construir los párrafos. Se conserva el granate UNSA. No emite cartas oficiales, firmas digitales ni reglamentos no confirmados. La copia cerrada no se reconstruye desde datos actuales; no existe reapertura en este circuito.

## Revisión manual

1. Supervisor: panel → Evaluar practicantes y ver expedientes → práctica vinculada → Completar evaluación → revisar → confirmar. Probar conclusión que requiere mejoras y posterior actualización favorable.
2. Alumno: panel → Mi expediente de prácticas. Revisar requisitos, evaluación, enlaces a bitácora/tareas/metas y descargar el PDF en curso.
3. Docente: seguimiento individual → evaluación y cierre → seleccionar requisitos y criterio académico. Comprobar pendientes concretos y acción de cierre deshabilitada cuando falta alguno.
4. Con un expediente ficticio completo, revisar y confirmar cierre. Descargar final; comprobar responsables, notas, metas y horas. No cerrar un caso que todavía se necesite editar para otras revisiones manuales.

Validación automática reservada al final del desarrollo, por indicación del usuario.

Al finalizar: 8 pruebas de `test_expediente_flow.py` y 8 de `test_hours_flow.py` aprobadas con SQLite aislado, sin escrituras en Supabase. TypeScript de la app correcto. La migración aditiva se aplicó al esquema de pruebas sin reinicializar ni cargar semilla.
