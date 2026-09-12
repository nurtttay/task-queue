# Task Queue

Собственная система очередей задач на Python (упрощённый аналог Celery),
с приоритетами, отложенными задачами, retry с экспоненциальным backoff,
Dead Letter Queue и веб-панелью мониторинга.

## Возможности

- 🎯 Приоритеты задач: `high` / `normal` / `low`
- ⏱ Отложенные/запланированные задачи (`delay_seconds`)
- 🔁 Retry с экспоненциальным backoff при падении задачи
- ☠️ Dead Letter Queue — задачи, упавшие после всех попыток
- 🔒 Идемпотентность через `idempotency_key` — защита от дублей
- 🧵 Несколько воркеров параллельно (горизонтальное масштабирование)
- 🛑 Graceful shutdown воркеров (SIGINT/SIGTERM)
- 📊 REST API + веб-дашборд для мониторинга очереди

## Структура проекта

```
task-queue/
├── api/
│   ├── main.py          # FastAPI приложение
│   ├── routes.py        # эндпоинты
│   └── schemas.py       # Pydantic модели запросов/ответов
├── worker/
│   ├── worker.py         # процесс-воркер
│   └── tasks.py          # реестр обработчиков задач
├── core/
│   ├── queue.py          # логика работы с Redis (enqueue/dequeue/retry/dlq)
│   └── models.py         # Task, TaskStatus, Priority
├── dashboard/
│   └── index.html        # веб-панель мониторинга
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── test_queue_manual.py  # smoke-тесты на fakeredis
```

## Быстрый старт (Docker)

```bash
docker-compose up --build
# или с несколькими воркерами:
docker-compose up --build --scale worker=3
```

- API: http://localhost:8000/docs (Swagger)
- Дашборд: http://localhost:8000/

## Локальный запуск без Docker

```bash
pip install -r requirements.txt

# 1. Запустить Redis (локально или в контейнере)
docker run -p 6379:6379 redis:7-alpine

# 2. Запустить API
uvicorn api.main:app --reload

# 3. Запустить воркер (в отдельном терминале, можно несколько)
python -m worker.worker worker-1
```

## Пример использования API

Создать задачу:
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "send_email",
    "payload": {"to": "user@example.com", "subject": "Привет!"},
    "priority": "high"
  }'
```

Отложенная задача (выполнится через 30 секунд):
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"task_type": "send_email", "payload": {"to": "a@b.com"}, "delay_seconds": 30}'
```

Проверить статус:
```bash
curl http://localhost:8000/api/tasks/{task_id}
```

Метрики очереди:
```bash
curl http://localhost:8000/api/stats
```

## Добавление своего типа задачи

В `worker/tasks.py`:
```python
@register("my_task")
def my_task(payload: dict):
    # твоя логика
    return {"done": True}
```
После этого можно ставить задачи с `"task_type": "my_task"` через API.

## Тесты

```bash
pip install -r requirements-dev.txt
python test_queue_manual.py
```

## Возможные улучшения

- Периодические (cron-like) задачи
- Приоритезация внутри одного приоритета по времени создания (FIFO гарантирован списками Redis)
- Хранение полной истории выполнения (сейчас хранится только последнее состояние)
- Аутентификация API (API-ключи)
- Экспорт метрик в Prometheus
