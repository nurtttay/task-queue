# Task Queue

A custom Python task queue system (a lightweight Celery-like alternative) built on Redis, with priorities, scheduled tasks, retry with exponential backoff, a Dead Letter Queue, and a web dashboard.

## Features

- 🎯 Task priorities: `high` / `normal` / `low`
- ⏱ Scheduled/delayed tasks (`delay_seconds`)
- 🔁 Retry with exponential backoff on failure
- ☠️ Dead Letter Queue — tasks that failed after all retry attempts
- 🔒 Idempotency via `idempotency_key` — prevents duplicate task creation
- 🧵 Multiple workers running in parallel (horizontal scaling)
- 🛑 Graceful worker shutdown (SIGINT/SIGTERM)
- 📊 REST API + web dashboard for monitoring the queue

## Project Structure

```
task-queue/
├── api/
│   ├── main.py          # FastAPI application
│   ├── routes.py        # endpoints
│   └── schemas.py       # Pydantic request/response models
├── worker/
│   ├── worker.py         # worker process
│   └── tasks.py          # task handler registry
├── core/
│   ├── queue.py          # Redis queue logic (enqueue/dequeue/retry/dlq)
│   └── models.py         # Task, TaskStatus, Priority
├── dashboard/
│   └── index.html        # monitoring web dashboard
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── test_queue_manual.py  # smoke tests using fakeredis
```

## Quick Start (Docker)

```bash
docker-compose up --build
# or with multiple workers:
docker-compose up --build --scale worker=3
```

- API / Swagger docs: http://localhost:8000/docs
- Dashboard: http://localhost:8000/

Other useful commands:

```bash
docker-compose up --build -d      # run in background
docker-compose logs -f            # follow logs
docker-compose logs -f worker     # worker logs only
docker-compose down               # stop
docker-compose down -v            # stop and wipe Redis data
```

## Local Setup (without Docker)

```bash
pip install -r requirements.txt

# 1. Start Redis
docker run -p 6379:6379 redis:7-alpine

# 2. Start the API
uvicorn api.main:app --reload

# 3. Start a worker (in a separate terminal, you can run several)
python -m worker.worker worker-1
```

## API Usage Examples

Create a task:
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "send_email",
    "payload": {"to": "user@example.com", "subject": "Hello!"},
    "priority": "high"
  }'
```

Schedule a task 30 seconds in the future:
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"task_type": "send_email", "payload": {"to": "a@b.com"}, "delay_seconds": 30}'
```

Check task status:
```bash
curl http://localhost:8000/api/tasks/{task_id}
```

Queue metrics:
```bash
curl http://localhost:8000/api/stats
```

## Adding a New Task Type

In `worker/tasks.py`:
```python
@register("my_task")
def my_task(payload: dict):
    # your logic here
    return {"done": True}
```
Once registered, you can enqueue it via the API with `"task_type": "my_task"`.

## Running Tests

```bash
pip install -r requirements-dev.txt
python test_queue_manual.py
```

## Possible Improvements

- Periodic (cron-like) tasks
- Full execution history (currently only the latest state is stored)
- API authentication (API keys)
- Prometheus metrics export
