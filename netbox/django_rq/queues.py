from __future__ import annotations
from typing import Any
from utilities.fakeredis_shim import get_queue as _get_queue, get_connection as _get_conn, get_redis_connection as _get_redis


def get_connection(*args: Any, **kwargs: Any):
    return _get_conn()


def get_redis_connection(*args: Any, **kwargs: Any):
    return _get_redis()


def get_queue(name: str = "default"):
    """Get a queue by name using the singleton pattern from fakeredis_shim."""
    return _get_queue(name)


def get_queue_by_index(index: int):
    """Get a queue by index (0=default, 1=high, 2=low)."""
    names = {0: "default", 1: "high", 2: "low"}
    return _get_queue(names.get(index, "default"))
