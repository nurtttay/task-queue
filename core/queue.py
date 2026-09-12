"""
Логика работы очереди задач на Redis.

Структуры данных в Redis:
- queue:{priority}      -> LIST, очередь task_id по приоритету (LPUSH/BRPOP)
- scheduled              -> ZSET, task_id -> run_at (отложенные задачи)
- tasks:{task_id}        -> STRING (JSON), сама задача
- dlq                    -> LIST, task_id задач, упавших после всех retry
- idempotency:{key}      -> STRING task_id, TTL, для защиты от дублей
- stats:*                -> счётчики (INCR)

Порядок приоритетов при выборе задачи воркером: high -> normal -> low.
"""
from __future__ import annotations

from typing import Optional

import redis

from core.models import Task, TaskStatus, Priority

PRIORITY_ORDER = [Priority.HIGH, Priority.NORMAL, Priority.LOW]

TASK_KEY = "tasks:{}"
QUEUE_KEY = "queue:{}"
SCHEDULED_KEY = "scheduled"
DLQ_KEY = "dlq"
IDEMPOTENCY_KEY = "idempotency:{}"
IDEMPOTENCY_TTL = 24 * 60 * 60  # сутки


class TaskQueue:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.r = redis.from_url(redis_url, decode_responses=True)

    # ---------- Постановка задач ----------

    def enqueue(self, task: Task, idempotency_key: Optional[str] = None) -> Task:
        """
        Добавить задачу в очередь.
        Если передан idempotency_key и задача с таким ключом уже есть —
        вернуть существующую задачу вместо создания новой.
        """
        if idempotency_key:
            existing_id = self.r.get(IDEMPOTENCY_KEY.format(idempotency_key))
            if existing_id:
                existing = self.get_task(existing_id)
                if existing:
                    return existing

        if task.run_at:
            task.status = TaskStatus.SCHEDULED
            self._save(task)
            self.r.zadd(SCHEDULED_KEY, {task.task_id: task.run_at})
        else:
            task.status = TaskStatus.PENDING
            self._save(task)
            self.r.lpush(QUEUE_KEY.format(task.priority.value), task.task_id)

        if idempotency_key:
            self.r.set(IDEMPOTENCY_KEY.format(idempotency_key), task.task_id, ex=IDEMPOTENCY_TTL)

        self.r.incr("stats:enqueued")
        return task

    def promote_scheduled(self) -> int:
        """
        Перенести из scheduled в реальные очереди задачи, время которых пришло.
        Вызывается периодически (например, воркером-планировщиком или самим воркером).
        Возвращает кол-во перенесённых задач.
        """
        import time
        now = time.time()
        due_ids = self.r.zrangebyscore(SCHEDULED_KEY, min=0, max=now)
        count = 0
        for task_id in due_ids:
            task = self.get_task(task_id)
            if not task:
                self.r.zrem(SCHEDULED_KEY, task_id)
                continue
            task.status = TaskStatus.PENDING
            self._save(task)
            self.r.lpush(QUEUE_KEY.format(task.priority.value), task.task_id)
            self.r.zrem(SCHEDULED_KEY, task_id)
            count += 1
        return count

    # ---------- Выборка задач воркером ----------

    def dequeue(self, timeout: int = 5) -> Optional[Task]:
        """
        Забрать одну задачу с учётом приоритета.
        BRPOP блокируется до timeout секунд, если очереди пусты.
        """
        keys = [QUEUE_KEY.format(p.value) for p in PRIORITY_ORDER]
        result = self.r.brpop(keys, timeout=timeout)
        if not result:
            return None
        _, task_id = result
        task = self.get_task(task_id)
        if not task:
            return None
        task.status = TaskStatus.RUNNING
        self._save(task)
        return task

    # ---------- Завершение задач ----------

    def mark_success(self, task: Task, result=None) -> None:
        task.status = TaskStatus.SUCCESS
        task.result = result
        self._save(task)
        self.r.incr("stats:success")

    def mark_failed(self, task: Task, error: str) -> None:
        """
        Обработка провала: либо ставим на retry с backoff, либо в DLQ.
        """
        task.error = error
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.RETRYING
            delay = task.next_backoff_delay()
            import time
            task.run_at = time.time() + delay
            self._save(task)
            self.r.zadd(SCHEDULED_KEY, {task.task_id: task.run_at})
            self.r.incr("stats:retried")
        else:
            task.status = TaskStatus.FAILED
            self._save(task)
            self.r.lpush(DLQ_KEY, task.task_id)
            self.r.incr("stats:failed")

    def cancel(self, task_id: str) -> bool:
        """Отменить задачу, если она ещё не взята в работу."""
        task = self.get_task(task_id)
        if not task or task.status not in (TaskStatus.PENDING, TaskStatus.SCHEDULED):
            return False
        task.status = TaskStatus.CANCELLED
        self._save(task)
        # Из списков Redis удалить конкретный элемент можно через LREM
        self.r.lrem(QUEUE_KEY.format(task.priority.value), 0, task_id)
        self.r.zrem(SCHEDULED_KEY, task_id)
        return True

    # ---------- Чтение ----------

    def get_task(self, task_id: str) -> Optional[Task]:
        raw = self.r.get(TASK_KEY.format(task_id))
        if not raw:
            return None
        return Task.from_json(raw)

    def get_stats(self) -> dict:
        pipe = self.r.pipeline()
        for p in PRIORITY_ORDER:
            pipe.llen(QUEUE_KEY.format(p.value))
        pipe.zcard(SCHEDULED_KEY)
        pipe.llen(DLQ_KEY)
        pipe.get("stats:enqueued")
        pipe.get("stats:success")
        pipe.get("stats:failed")
        pipe.get("stats:retried")
        (
            high, normal, low, scheduled, dlq,
            enqueued, success, failed, retried,
        ) = pipe.execute()
        return {
            "queue_high": high,
            "queue_normal": normal,
            "queue_low": low,
            "scheduled": scheduled,
            "dlq": dlq,
            "total_enqueued": int(enqueued or 0),
            "total_success": int(success or 0),
            "total_failed": int(failed or 0),
            "total_retried": int(retried or 0),
        }

    def list_dlq(self, limit: int = 50) -> list[Task]:
        ids = self.r.lrange(DLQ_KEY, 0, limit - 1)
        return [t for t in (self.get_task(i) for i in ids) if t]

    # ---------- Внутреннее ----------

    def _save(self, task: Task) -> None:
        import time
        task.updated_at = time.time()
        self.r.set(TASK_KEY.format(task.task_id), task.to_json())
