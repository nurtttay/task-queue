"""
Ручной smoke-тест core/queue.py на fakeredis (без реального Redis).
Запуск: python test_queue_manual.py
"""
import time
import fakeredis

from core.queue import TaskQueue
from core.models import Task, Priority, TaskStatus


def make_queue() -> TaskQueue:
    tq = TaskQueue.__new__(TaskQueue)
    tq.r = fakeredis.FakeStrictRedis(decode_responses=True)
    return tq


def test_basic_enqueue_dequeue():
    tq = make_queue()
    t = Task(task_type="send_email", payload={"to": "a@b.com"}, priority=Priority.NORMAL)
    tq.enqueue(t)

    got = tq.dequeue(timeout=1)
    assert got is not None
    assert got.task_id == t.task_id
    assert got.status == TaskStatus.RUNNING
    print("OK: basic enqueue/dequeue")


def test_priority_order():
    tq = make_queue()
    low = Task(task_type="x", priority=Priority.LOW)
    high = Task(task_type="x", priority=Priority.HIGH)
    normal = Task(task_type="x", priority=Priority.NORMAL)
    tq.enqueue(low)
    tq.enqueue(normal)
    tq.enqueue(high)

    first = tq.dequeue(timeout=1)
    assert first.task_id == high.task_id, "high priority должен идти первым"
    second = tq.dequeue(timeout=1)
    assert second.task_id == normal.task_id
    third = tq.dequeue(timeout=1)
    assert third.task_id == low.task_id
    print("OK: priority order (high -> normal -> low)")


def test_idempotency():
    tq = make_queue()
    t1 = Task(task_type="charge", payload={"amount": 100})
    saved = tq.enqueue(t1, idempotency_key="order-42")

    t2 = Task(task_type="charge", payload={"amount": 100})
    saved2 = tq.enqueue(t2, idempotency_key="order-42")

    assert saved.task_id == saved2.task_id, "должна вернуться та же задача"
    print("OK: idempotency prevents duplicate enqueue")


def test_retry_and_dlq():
    tq = make_queue()
    t = Task(task_type="flaky", max_retries=2)
    tq.enqueue(t)
    task = tq.dequeue(timeout=1)

    # первая неудача -> retrying
    tq.mark_failed(task, "boom 1")
    updated = tq.get_task(task.task_id)
    assert updated.status == TaskStatus.RETRYING
    assert updated.retry_count == 1

    # вторая неудача -> retrying (retry_count=2, max=2)
    tq.mark_failed(updated, "boom 2")
    updated = tq.get_task(task.task_id)
    assert updated.status == TaskStatus.RETRYING
    assert updated.retry_count == 2

    # третья неудача -> должна уйти в DLQ (retry_count >= max_retries)
    tq.mark_failed(updated, "boom 3")
    updated = tq.get_task(task.task_id)
    assert updated.status == TaskStatus.FAILED
    dlq = tq.list_dlq()
    assert any(d.task_id == task.task_id for d in dlq)
    print("OK: retry with backoff, then DLQ after max_retries")


def test_scheduled_task_promotion():
    tq = make_queue()
    t = Task(task_type="delayed_job", run_at=time.time() - 1)  # уже "просрочено"
    tq.enqueue(t)

    stats_before = tq.get_stats()
    assert stats_before["scheduled"] == 1

    promoted = tq.promote_scheduled()
    assert promoted == 1

    task = tq.dequeue(timeout=1)
    assert task.task_id == t.task_id
    print("OK: scheduled task promoted to queue and dequeued")


def test_cancel():
    tq = make_queue()
    t = Task(task_type="cancel_me")
    tq.enqueue(t)
    ok = tq.cancel(t.task_id)
    assert ok
    task = tq.get_task(t.task_id)
    assert task.status == TaskStatus.CANCELLED
    # не должна больше выниматься из очереди
    got = tq.dequeue(timeout=1)
    assert got is None
    print("OK: cancel removes task from queue")


if __name__ == "__main__":
    test_basic_enqueue_dequeue()
    test_priority_order()
    test_idempotency()
    test_retry_and_dlq()
    test_scheduled_task_promotion()
    test_cancel()
    print("\nВсе тесты прошли успешно!")
