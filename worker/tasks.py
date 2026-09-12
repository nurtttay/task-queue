"""
Реестр обработчиков задач.

Чтобы добавить новый тип задачи:
1. Написать функцию, принимающую payload: dict и возвращающую результат (любой JSON-сериализуемый объект).
2. Зарегистрировать её через @register("имя_типа").

Пример:
    @register("send_email")
    def send_email(payload: dict):
        ...
        return {"sent": True}
"""
from __future__ import annotations

import time
from typing import Any, Callable

TASK_REGISTRY: dict[str, Callable[[dict], Any]] = {}


def register(task_type: str):
    def decorator(func: Callable[[dict], Any]):
        TASK_REGISTRY[task_type] = func
        return func
    return decorator


def get_handler(task_type: str) -> Callable[[dict], Any] | None:
    return TASK_REGISTRY.get(task_type)


# ---------- Примеры задач (замени/дополни своими) ----------

@register("send_email")
def send_email(payload: dict) -> dict:
    to = payload.get("to")
    subject = payload.get("subject", "(no subject)")
    # Здесь была бы реальная отправка письма (smtplib / API провайдера)
    time.sleep(0.5)
    return {"sent_to": to, "subject": subject}


@register("resize_image")
def resize_image(payload: dict) -> dict:
    path = payload.get("path")
    width = payload.get("width", 100)
    # Здесь была бы реальная обработка изображения (Pillow и т.п.)
    time.sleep(1)
    return {"resized": path, "width": width}


@register("flaky_demo")
def flaky_demo(payload: dict) -> dict:
    """Задача для демонстрации retry: падает по чётным попыткам."""
    import random
    if random.random() < 0.6:
        raise RuntimeError("случайный сбой для демонстрации retry")
    return {"ok": True}
