"""Run from repository root: python -m uvicorn backend.main:app --host 127.0.0.1."""
from .app import create_app

app = create_app()
