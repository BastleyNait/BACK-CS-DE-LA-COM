# Navegación del alumno · Incremento 21

Lecturas para el Inicio y la Bitácora de la app Expo. Disponibles bajo `/api/v1/alumno`, con JWT y rol ALUMNO; no sustituyen las rutas de escritura y revisión de horas existentes.

| Ruta GET | Respuesta |
| --- | --- |
| `/inicio` | Aulas matriculadas, práctica abierta o última cerrada, resumen de horas por estado, última actividad rechazada y primera tarea de un aula activa sin entrega propia. |
| `/practicas/{id}/bitacora` | Práctica, resumen global por estado, coincidencias, registros y cursor siguiente. |
| `/practicas/{id}/actividad/{registroId}` | Práctica y actividad propia. |

Bitácora acepta `limite` de 1 a 50 (predeterminado 20), `estado` PENDIENTE/VALIDADO/RECHAZADO y `cursor`. Ordena por fecha e identificador descendentes y consulta `limite + 1` filas para determinar si hay otra página. El cursor contiene la fecha y el identificador de la última fila; un formato inválido recibe 422. Los totales se agregan en SQL sobre todos los registros de la práctica y permanecen independientes del filtro y del cursor.

Los permisos se comprueban antes de devolver información; una práctica ajena recibe 404 y otro rol recibe 403. La tarea pendiente excluye cualquier entrega propia ya existente. No se añaden tablas, índices, migraciones ni datos semilla. El rendimiento con grandes volúmenes y los índices adicionales se revisarán con mediciones; la consulta no descarga todo el historial en memoria.

## Verificación focal

Con Python de Windows, desde este repositorio:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_student_navigation.py
```

Cuatro casos SQLite en memoria correctos: 45 actividades con empate de fecha se recorren en páginas 20/20/5 sin duplicados, totales independientes del filtro, aislamiento por usuario/rol, validación del cursor y selección de tareas. Sin escrituras en Supabase. La app comprueba además las lecturas reales con cuentas ficticias locales; no se publica producción ni se fusiona esta rama con main.
