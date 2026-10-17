# Mensajería privada · incremento 16

Sin migración. Reutiliza MensajeDirecto, su indicador leido y Auditoria. La mensajería académica solo permite ALUMNO/PROFESOR y el vínculo vigente docente responsable/alumno matriculado. Administración usa anuncios/foros; este módulo no expone conversaciones privadas de terceros.

- GET /mensajes/capacidades: versionMensajes=1, lecturaExplicita=true.
- GET /aulas/{aulaId}/contactos: docente ve alumnos matriculados; alumno ve su docente. Contadores sin leer agrupados por remitente, solo para el destinatario autenticado.
- GET /aulas/{aulaId}/mensajes/{otroId}: lista cronológica de la pareja, sin marcar leído. Verifica rol, pertenencia y relación de contacto antes de consultar. Cambia la conducta antigua de GET; los clientes deben usar la lectura explícita.
- POST sobre esa ruta: texto no vacío hasta 10000 caracteres y solicitudId opcional. Bloquea aula, verifica vínculo y estado activo. ID derivado de autor/aula/contacto/solicitud; repetir exactamente devuelve el registro (201), otros datos con la misma clave dan 409.
- PUT /aulas/{aulaId}/mensajes/{otroId}/lectura: mensajeIds, entre 1 y 200 IDs distintos. Bloquea aula/mensajes y exige aula, remitente/contacto y destinatario actual correctos para todos los IDs. Si alguno no está disponible, 404 sin cambios parciales. Repetir es inocuo; no escribe Auditoria. Permite confirmar lectura en aula concluida.

Respuesta de mensaje: id, aulaId, remitenteId/nombre, destinatarioId, texto, mio, leido y fecha. El cliente verifica las identidades de ambos extremos. Reasignar docente o retirar matrícula revoca el acceso histórico por esas rutas; no borra el contenido persistido.

Cada envío efectivo genera MENSAJE_ENVIADO con metadatos de las cuentas y aula; se excluye el texto privado. No se copian adjuntos ni se envía push, correo o comunicación a servicios externos. La app no presenta esto como tiempo real.

Pruebas: python -m unittest discover -s tests -p test_direct_messages.py (7 casos), test:mensajes y recorrido real aislado documentado en la app. Conservar secretos y evidencias fuera de Git. Integración/publicación de producción sigue separada.
