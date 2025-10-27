from __future__ import annotations
from typing import Any
from utilities.fakeredis_shim import Worker
from .queues import get_queue


def get_worker(queue_name: str = "default", name: Any = None, **kwargs: Any) -> Worker:
    """Get a worker for the specified queue."""
    queue = get_queue(queue_name)
    return Worker([queue], name=name, connection=queue.connection)
