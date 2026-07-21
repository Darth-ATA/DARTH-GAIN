"""Jinja2 templates configuration for the web dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from starlette.responses import HTMLResponse

# Resolve the templates directory relative to this file
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def render_template(
    name: str,
    context: dict[str, Any],
    status_code: int = 200,
) -> HTMLResponse:
    """Render a Jinja2 template and return an HTMLResponse.

    Args:
        name: Template file name (e.g. ``"login.html"``).
        context: Template variables.
        status_code: HTTP status code (default 200).

    Returns:
        An HTML response with the rendered template.
    """
    template = _env.get_template(name)
    html = template.render(**context)
    return HTMLResponse(html, status_code=status_code)
