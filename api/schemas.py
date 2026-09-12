"""
Pydantic-схемы запросов/ответов для API.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from core.models import Priority, TaskStatus


class CreateTaskRequest(BaseModel):
    task_type: str = Field(..., examples=["send_email"])
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    max_retries: int = Field(default=3, ge=0, le=10)
    delay_seconds: Optional[float] = Field(
        default=None, ge=0,
        description="Через сколько секунд выполнить задачу (для отложенных задач)",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Если задача с таким ключом уже создана — вернётся существующая",
    )


class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: TaskStatus
    priority: Priority
    payload: dict[str, Any]
    retry_count: int
    max_retries: int
    created_at: float
    updated_at: float
    run_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class StatsResponse(BaseModel):
    queue_high: int
    queue_normal: int
    queue_low: int
    scheduled: int
    dlq: int
    total_enqueued: int
    total_success: int
    total_failed: int
    total_retried: int
