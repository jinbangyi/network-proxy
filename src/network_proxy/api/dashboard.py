from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

router = APIRouter(tags=["dashboard"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    """Serve the admin dashboard shell.

    No server-side auth: this route only returns static HTML. Every API call
    made from the page is authenticated via the existing ``require_admin``
    dependency on ``/admin/*`` endpoints.
    """
    template = _env.get_template("dashboard.html")
    return HTMLResponse(template.render())
