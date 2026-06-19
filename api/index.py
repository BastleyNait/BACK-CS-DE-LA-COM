"""
Entrypoint para Vercel (Serverless Functions — runtime @vercel/python).

Vercel detecta automáticamente la variable `app` (una aplicación ASGI) y la
sirve. Todas las rutas se reescriben hacia este archivo vía `vercel.json`,
así que FastAPI sigue resolviendo `/`, `/docs`, `/api/v1/...` con normalidad.

En desarrollo local se sigue usando `uvicorn app.main:app --reload`; este
archivo solo se usa en el despliegue.
"""

from app.main import app

# Exponer explícitamente el callable ASGI que Vercel buscará.
__all__ = ["app"]
