# In-memory django_rq shim backed by fakeredis for tests/dev without a real Redis server.
from .queues import get_queue, get_connection, get_redis_connection, get_queue_by_index  # noqa: F401
from .utils import get_statistics, get_jobs, stop_jobs  # noqa: F401
from .settings import QUEUES_LIST, QUEUES_MAP  # noqa: F401

# Pass-through decorator for jobs

def job(*dargs, **dkwargs):
    def _wrap(func):
        return func
    return _wrap

# Worker helper compatible API
from .workers import get_worker  # noqa: E402,F401
