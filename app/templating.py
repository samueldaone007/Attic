"""Shared Jinja2 template environment."""

from fastapi.templating import Jinja2Templates

from . import config

templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
templates.env.globals["app_name"] = config.APP_NAME
templates.env.globals["tagline"] = config.TAGLINE
