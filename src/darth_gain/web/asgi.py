"""ASGI entry point for DARTH-GAIN web dashboard.

This module creates the application instance at import time,
suitable for use by uvicorn/gunicorn ASGI servers:

    uvicorn darth_gain.web.asgi:app
"""

from darth_gain.web.app import create_app

app = create_app()
