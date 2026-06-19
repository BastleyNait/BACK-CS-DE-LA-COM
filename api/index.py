"""
Entrypoint para Vercel (Serverless Functions — runtime @vercel/python).

Vercel ejecuta esta función desde el directorio `api/`, así que el paquete
`app/` (que vive en el root del proyecto) no está en `sys.path` por defecto y
`from app.main import app` falla con ModuleNotFoundError. Añadimos el root al
path antes de importar para evitarlo.

Vercel detecta la variable `app` (aplicación ASGI) y la sirve. Todas las rutas
se reescriben hacia este archivo vía `vercel.json`, así que FastAPI sigue
resolviendo `/`, `/docs`, `/api/v1/...` con normalidad.

En desarrollo local se sigue usando `uvicorn app.main:app --reload`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

# Exponer explícitamente el callable ASGI que Vercel buscará.
__all__ = ["app"]
