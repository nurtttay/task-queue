"""
REST API для работы с очередью задач.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from core.models import Task
from core.queue import TaskQueue
from api.schemas import CreateTaskRequest, TaskResponse, StatsResponse

router = APIRouter()

# Единый экземпляр очереди на процесс API (Redis-соединение переиспользуется).
# REDIS_URL берётся из main.py при создании приложения.
_queue: TaskQueue | None = None


def get_queue() -> TaskQueue:
    if _queue is None:
        raise RuntimeError("TaskQueue не инициализирована")
    return _queue


def init_queue(redis_url: str) -> None:
    global _queue
    _queue = TaskQueue(redis_url=redis_url)


def _to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        payload=task.payload,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        created_at=task.created_at,
        updated_at=task.updated_at,
        run_at=task.run_at,
        result=task.result,
        error=task.error,
    )


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(req: CreateTaskRequest):
    run_at = time.time() + req.delay_seconds if req.delay_seconds else None
    task = Task(
        task_type=req.task_type,
        payload=req.payload,
        priority=req.priority,
        max_retries=req.max_retries,
        run_at=run_at,
    )
    saved = get_queue().enqueue(task, idempotency_key=req.idempotency_key)
    return _to_response(saved)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    task = get_queue().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return _to_response(task)


@router.delete("/tasks/{task_id}", response_model=TaskResponse)
def cancel_task(task_id: str):
    task = get_queue().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    ok = get_queue().cancel(task_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя отменить задачу в статусе '{task.status.value}'",
        )
    return _to_response(get_queue().get_task(task_id))


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    return get_queue().get_stats()


@router.get("/dlq", response_model=list[TaskResponse])
def get_dlq(limit: int = 50):
    tasks = get_queue().list_dlq(limit=limit)
    return [_to_response(t) for t in tasks]
