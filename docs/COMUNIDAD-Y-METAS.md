# Comunidad y metas · incremento 14

Se reutilizan Anuncio, ForoHilo, ForoMensaje, Meta y Auditoria. Sin migración ni reinicialización. Los cambios permanecen en la rama de desarrollo.

## Comunidad del aula

- `GET /comunicacion/capacidades`: `versionComunicacion: 1`.
- `GET /comunicacion/aulas`: solo aulas de la matrícula del alumno, propias del docente o todas para administración. Supervisor recibe 403.
- `GET/POST /aulas/{aulaId}/anuncios`: consulta por pertenencia; publica solo docente responsable/administración. Título 1–200, mensaje 1–10000, fijado booleano estricto. Primero fijados, después fecha descendente.
- `GET/POST /aulas/{aulaId}/foros`: miembros consultan/abren temas de 1–200 caracteres. El número de respuestas se obtiene con agregación, sin una consulta por hilo.
- `GET/POST /foros/{hiloId}/mensajes`: pertenencia al aula del hilo; respuesta 1–10000 caracteres. Mensajes ordenados cronológicamente.

Los POST admiten `solicitudId` (16–80 caracteres alfanuméricos/guiones). El ID deriva de autor, recurso padre y solicitud. Bajo bloqueo del aula, una repetición idéntica devuelve el mismo objeto (201); otros datos con la misma solicitud producen 409. Una clave compartida por cuentas o aulas distintas no cruza sus recursos. Un reintento confirmado no genera otra auditoría.

El bloqueo del aula se adquiere antes de comprobar permisos/matrícula y estado, y es el mismo que usan administración/asistencia. Un aula concluida permite consulta y bloquea nuevas publicaciones/respuestas/eliminaciones. Las repeticiones de publicaciones guardadas no modifican el contenido.

La eliminación de anuncios existente conserva permiso docente/administración, bloqueo de aula y auditoría; la app nueva no añade un control de eliminación. La mensajería directa anterior mantiene sus rutas y no se presenta como un módulo nuevo.

## Metas por práctica

- `GET /metas/capacidades`: `versionMetas: 1, avanceTotal: true`.
- `GET /metas`, `/metas/practicante/{id}` y `/metas/practica/{id}` aplican el alcance de prácticas: alumno propietario, docente responsable, supervisor vinculado o administración. El listado por practicante ya no expone metas ajenas.
- `POST /metas/practica/{id}`: solo docente responsable/administración, práctica abierta. Tipo ARTICULOS/NOTAS_PERIODISTICAS/NOTAS_PRENSA/HORAS; objetivo entero estricto 1–1000000; descripción opcional hasta 2000. `solicitudId` admite reintentos del mismo objetivo sin crear duplicados.
- `PUT /metas/{id}/avance-total`: cantidad total entera 0–1000000, `anterior` esperado y motivo no vacío hasta 2000. Solo docente responsable/administración, práctica abierta y meta no HORAS. Guarda el total absoluto, no un incremento. Si el resultado ya coincide, no escribe; si el valor actual difiere de anterior, 409.
- `PUT /metas/{id}/avance` queda bloqueado con 409 para evitar que clientes antiguos dupliquen producción al reintentar incrementos acumulativos.

Crear/actualizar bloquea primero práctica y después meta cuando corresponde, en el mismo orden del resto del ciclo de horas/cierre. Las metas HORAS suman registros VALIDADO; nunca aceptan avance manual. El contador de producción es seguimiento docente, no verificación automática de archivos/evidencias. Completar metas no cierra una práctica.

## Auditoría y comprobación

Publicación, apertura de hilo, respuesta, alta de meta y cambio efectivo de avance guardan responsable y detalle en Auditoria, dentro de la misma transacción del dato. No se producen eventos por reintentos o rechazos. No se requiere un servicio externo ni se envían mensajes a personas fuera de la aplicación de pruebas.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_community_modules.py
```

Nueve casos SQLite aislados: permisos, reintentos, respuestas, cierre, cantidades, listados por alcance, avance absoluto, conflictos y horas validadas. La app añade un recorrido Chromium simulado y uno real sobre ssp_test; ver su docs/INCREMENTO-14.md. Las cuentas y contenido son ficticios. Producción requiere integración/publicación autorizada.
