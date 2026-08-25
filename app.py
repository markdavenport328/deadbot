"""Vercel entrypoint for the Deadbot FastAPI application."""

from deadbot.api import app

__all__ = ["app"]
