# Comunicación y documentos con carga progresiva

Desarrollo posterior a la presentación del 23 de octubre. Mantener las rutas anteriores por compatibilidad.

El router `module_pages` añade páginas de anuncios, temas, respuestas, mensajes privados y archivos, más los detalles individuales de anuncio/tema. Usa las comprobaciones existentes de pertenencia al aula y vínculo docente/alumno. No cambia escrituras ni criterios de acceso.

Cada consulta recibe `limite` (1–40, cliente20) y `cursor`; devuelve `items`, `total` y `siguiente`. El cursor contiene fecha/identificador y el hash del ámbito formado por usuario, recurso y filtro. Se rechaza su uso en otra consulta. El orden es fecha/id descendente y, para anuncios, fijados primero. Se consulta una fila adicional para determinar si queda otra página. El total corresponde al conjunto autorizado y al filtro, no a la página visible.

Los anuncios seleccionan un extracto SQL de 180 caracteres; su texto completo se pide por la ruta de detalle. Los temas incluyen conteo de respuestas mediante subconsulta, sin cargar los mensajes. Los archivos devuelven metadatos y respetan el indicador persistente de material, sin cargar `ContenidoArchivo.datos`. El filtro propios se limita al usuario actual. Los mensajes incluyen un contador global de recibidos sin leer y consultar una página no modifica lecturas.

No se agregan tablas, índices ni migraciones, ni se carga semilla. Las pruebas nuevas son seis casos SQLite con páginas 20/20/5, empates, filtros, total sin leer, ámbitos, lectura tras conclusión y revocación de acceso por retiro. Se comprueba que los datos binarios de archivos no se materializan al listar. La idempotencia y las rutas de escritura originales se conservan.

El cliente alumno añade borradores persistentes de comunicación y reutiliza las solicitudes idempotentes ya soportadas por `crear_hilo`, `responder_hilo` y `enviar_mensaje`. Los pendientes confirmados requieren una acción explícita. No hay push, sockets, correo ni sincronización de fondo.
