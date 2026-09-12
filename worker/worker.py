"""
Воркер: в цикле забирает задачи из Redis-очереди и выполняет их
через обработчики из worker/tasks.py.

Запуск: python -m worker.worker
Несколько воркеров можно запускать параллельно (в разных процессах/контейнерах) —
Redis гарантирует, что одна задача достанется только одному воркеру (BRPOP атомарен).
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time

from core.queue import TaskQueue
from core.models import Task
from worker.tasks import get_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("worker")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
POLL_TIMEOUT = int(os.environ.get("WORKER_POLL_TIMEOUT", "5"))
PROMOTE_INTERVAL = int(os.environ.get("WORKER_PROMOTE_INTERVAL", "1"))


class Worker:
    def __init__(self, queue: TaskQueue, worker_id: str = "worker-1"):
        self.queue = queue
        self.worker_id = worker_id
        self._running = True
        self._last_promote = 0.0

    def stop(self, *_args):
        log.info("[%s] Получен сигнал остановки, завершаю текущую задачу и выхожу...", self.worker_id)
        self._running = False

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        log.info("[%s] Воркер запущен, слушаю очередь...", self.worker_id)

        while self._running:
            self._maybe_promote_scheduled()

            task = self.queue.dequeue(timeout=POLL_TIMEOUT)
            if task is None:
                continue  # таймаут, очередь пуста — идём на новый круг

            self._execute(task)

        log.info("[%s] Воркер остановлен.", self.worker_id)

    def _maybe_promote_scheduled(self):
        now = time.time()
        if now - self._last_promote >= PROMOTE_INTERVAL:
            moved = self.queue.promote_scheduled()
            if moved:
                log.info("[%s] Перенесено %d отложенных задач в очередь", self.worker_id, moved)
            self._last_promote = now

    def _execute(self, task: Task):
        handler = get_handler(task.task_type)
        if handler is None:
            log.error("[%s] Нет обработчика для типа задачи '%s'", self.worker_id, task.task_type)
            self.queue.mark_failed(task, error=f"unknown task_type: {task.task_type}")
            return

        log.info(
            "[%s] Выполняю задачу %s (тип=%s, попытка=%d/%d)",
            self.worker_id, task.task_id, task.task_type, task.retry_count + 1, task.max_retries + 1,
        )
        try:
            result = handler(task.payload)
            self.queue.mark_success(task, result=result)
            log.info("[%s] Задача %s выполнена успешно", self.worker_id, task.task_id)
        except Exception as exc:  # noqa: BLE001 — воркер должен пережить любую ошибку задачи
            log.warning("[%s] Задача %s упала: %s", self.worker_id, task.task_id, exc)
            self.queue.mark_failed(task, error=str(exc))


def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WORKER_ID", "worker-1")
    queue = TaskQueue(redis_url=REDIS_URL)
    Worker(queue, worker_id=worker_id).run()


if __name__ == "__main__":
    main()
