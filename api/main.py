"""
FastAPI приложение.

Запуск (после старта Redis):
    uvicorn api.main:app --reload

Или через docker-compose (см. docker-compose.yml в корне проекта).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router, init_queue

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = FastAPI(
    title="Task Queue API",
    description="Простая REST-обёртка над очередью задач на Redis",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    init_queue(REDIS_URL)


app.include_router(router, prefix="/api", tags=["tasks"])

# Отдаём статическую панель мониторинга
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")
if os.path.isdir(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

    @app.get("/")
    def dashboard():
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))
