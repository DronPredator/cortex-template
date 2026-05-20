"""Entry point legacy — mantiene compatibilidad con `uvicorn main:app`.

La lógica real vive en el paquete `app/`. Este archivo solo re-exporta.
"""

from app.main import app  # noqa: F401

__all__ = ["app"]
