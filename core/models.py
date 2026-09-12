"""
Модели данных для задач очереди.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"        # ждёт в очереди
    SCHEDULED = "scheduled"    # отложена, ждёт своего времени
    RUNNING = "running"        # взята воркером в работу
    SUCCESS = "success"        # выполнена успешно
    FAILED = "failed"          # упала после всех попыток -> DLQ
    RETRYING = "retrying"      # упала, но будет повторная попытка
    CANCELLED = "cancelled"    # отменена пользователем до выполнения


class Priority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class Task:
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    max_retries: int = 3
    retry_count: int = 0
    retry_backoff_base: float = 2.0  # секунды, растёт экспоненциально
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    run_at: Optional[float] = None   # для отложенных задач: unix timestamp
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_json(self) -> str:
        d = asdict(self)
        # enum -> str
        d["priority"] = self.priority.value if isinstance(self.priority, Priority) else self.priority
        d["status"] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        return json.dumps(d)

    @staticmethod
    def from_json(raw: str) -> "Task":
        d = json.loads(raw)
        d["priority"] = Priority(d["priority"])
        d["status"] = TaskStatus(d["status"])
        return Task(**d)

    def next_backoff_delay(self) -> float:
        """Экспоненциальный backoff: base * 2^retry_count"""
        return self.retry_backoff_base * (2 ** self.retry_count)
