"""ASGI entrypoint.

The application is assembled in the layered `api` package; this thin module keeps
the backend root importable and re-exports the FastAPI `app` so the service can be
launched as `uvicorn main:app` from the backend directory.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.app import app  # noqa: E402

__all__ = ["app"]
