# Lecturas paginadas del personal · incremento 28

`app/routers/staff_pages.py` añade lecturas bajo `/api/v1/equipo`. No modifica escrituras ni estructura de tablas.

| GET | Permiso y respuesta |
| --- | --- |
| `/aulas/pagina` | Docente propio o administración; resumen de aulas sin descripción larga. |
| `/aulas/{id}` | Detalle individual, con descripción; comprueba responsabilidad docente. |
| `/aulas/{id}/alumnos/pagina` | Padrón del aula solicitada, avance y conteos de tareas/entregas. |
| `/aulas/{id}/entregas/pagina` | Resúmenes, sin texto ni versiones; `pendientes=true` usa nota nula. |
| `/aulas/{id}/entregas/{entrega}` | Entrega del aula exacta y revisión máxima; no materializa versiones. |
| `/aulas/{id}/notas/pagina` | Resumen por matriculado, promedio de notas existentes, asistencia y horas validadas; promedio global independiente de búsqueda. |
| `/practicas/pagina` | Docente, supervisor o administración mediante `visible_practices`; horas sumadas solo para VALIDADO. |

Páginas `{items,total,siguiente}`, 20 por defecto y máximo40. Notas incluye `promedioGeneral`. Búsqueda `q` literal escapada, máximo120 después de recortar, sin distinción de mayúsculas según `lower` de la base. Prácticas filtra `estado=TODAS|ABIERTAS|CERRADAS`; alcanzar horas no concede autorización de cierre.

Cursores por clave de orden e ID, con ámbito hash de usuario/recurso/filtros. No son credenciales: todo permiso y filtro se aplica de nuevo en cada consulta. El total corresponde a los filtros sobre toda la consulta, no a la página. Los cambios concurrentes de nombres, fechas, notas o matrículas pueden alterar el conjunto: Actualizar reinicia la lista, no se promete una instantánea transaccional entre peticiones.

`tests/test_staff_pages.py` cubre 20/20/5 con empates, búsqueda literal, proyecciones sin cuerpos, detalle de aula/entrega exactos, revisión máxima sin contenido histórico, cero frente a nulo, promedio global con exclusión de no matriculados, asistencia, horas validadas, supervisión retirada, cambio de docente y cursores de otra consulta. Solo SQLite; la integración real consulta `ssp_test` sin nuevas escrituras académicas.
