# Lightweight shim to replace django_rq and redis connections with fakeredis for tests/dev.
# This keeps public APIs used in the project working without running a real Redis server.

from __future__ import annotations

import uuid
import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

try:
    import fakeredis
except Exception:  # pragma: no cover
    fakeredis = None  # type: ignore

# Global shared fake redis instance per process
_redis_instance = fakeredis.FakeRedis(decode_responses=True) if fakeredis else None

# Queue implementation compatible with django_rq minimal surface used in code
@dataclass
class _Job:
    id: str
    func_name: str
    args: tuple
    kwargs: dict
    status: str = "queued"
    sort_key: int = 0
    ts: str = ""

class FakeConnection:
    """Fake Redis connection for compatibility."""
    def flushall(self):
        """Clear all queues and registries."""
        # Clear all queues
        for queue in _QUEUES.values():
            queue._jobs.clear()
            queue._job_order.clear()
            queue._seq = 0
        
        # Clear all registries
        global _REGISTRIES
        _REGISTRIES.clear()

class FakeQueue:
    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._jobs: Dict[str, Job] = {}  # job_id -> Job
        self._job_order: List[str] = []  # Maintain insertion order explicitly
        self._seq: int = 0
        self.connection = FakeConnection()
        self.serializer = None  # RQ uses pickle by default, but we don't need it for tests

    @property
    def jobs(self) -> List[Job]:
        # FIFO: вернуть задачи в порядке постановки
        return [self._jobs[job_id] for job_id in self._job_order if job_id in self._jobs]

    @property
    def count(self) -> int:
        return len(self._jobs)

    def enqueue(self, func: Any, *args: Any, **kwargs: Any) -> Job:
        depends_on = kwargs.pop('depends_on', None)
        job_id = kwargs.pop('job_id', None) or uuid.uuid4().hex
        
        job = Job(id=job_id, connection=self.connection, origin=self.name, func=func)
        job.args = args
        job.kwargs = kwargs
        
        # If job depends on another job, set status to DEFERRED
        if depends_on:
            job.set_status(JobStatus.DEFERRED)
        else:
            job.set_status(JobStatus.QUEUED)
        
        self._jobs[job.id] = job
        self._job_order.append(job.id)
        return job

    def enqueue_at(self, schedule_at: Any, func: Any, *args: Any, **kwargs: Any) -> Job:
        """Schedule a job to run at a specific time. For fakeredis, add to scheduled registry."""
        job = self.enqueue(func, *args, **kwargs)
        job.scheduled_at = schedule_at
        # Add to scheduled registry
        scheduled_registry = ScheduledJobRegistry(self.name, connection=self.connection)
        scheduled_registry.add(job)
        return job

    def fetch_job(self, job_id: str) -> Optional[Job]:
        """Fetch a job by ID."""
        return self._jobs.get(job_id)

    @property
    def job_ids(self) -> List[str]:
        """Get list of job IDs."""
        return list(self._jobs.keys())

    def empty(self) -> None:
        self._jobs.clear()
        self._job_order.clear()

    # Совместимость с ожиданиями некоторых тестов
    def get_jobs(self) -> List[Job]:
        return self.jobs

# Global queues registry
_QUEUES: Dict[str, FakeQueue] = {}

# Shim functions mimicking django_rq

def get_queue(name: str = "default") -> FakeQueue:
    """Get or create a queue by name (singleton pattern)."""
    if name not in _QUEUES:
        _QUEUES[name] = FakeQueue(name)
    return _QUEUES[name]

def get_worker(queue_name: str = "default", name: Optional[str] = None, **kwargs) -> 'Worker':
    """Get or create a worker for the given queue."""
    queue = get_queue(queue_name)
    worker_name = name or queue_name
    worker_key = f'rq:worker:{worker_name}'
    if worker_key not in _WORKERS:
        worker = Worker([queue], name=worker_name)
        _WORKERS[worker_key] = worker
    else:
        worker = _WORKERS[worker_key]
    return worker

# Global workers registry
_WORKERS: Dict[str, 'Worker'] = {}

class Worker:
    def __init__(self, queues: Iterable[FakeQueue], name: Optional[str] = None, connection: Any = None):
        self.queues = list(queues)
        self.name = name or uuid.uuid4().hex
        self.connection = connection or _redis_instance
        self.birth_date = None
        self.key = f'rq:worker:{self.name}'
        self.total_working_time = 0  # in microseconds
        self._current_job = None
        self.state = 'idle'  # Worker state: 'idle', 'busy', 'started', 'suspended'
        self.successful_job_count = 0
        self.failed_job_count = 0
        self.pid = str(uuid.uuid4().int)[:5]  # Fake PID
        # Register this worker
        _WORKERS[self.key] = self

    def work(self, *args: Any, **kwargs: Any) -> None:
        """Execute jobs from the queue. For fakeredis, execute jobs if burst=True."""
        burst = kwargs.get('burst', False)
        if burst:
            # Execute all jobs in the queue
            for queue in self.queues:
                for job in list(queue.jobs):
                    try:
                        # Execute the job
                        if callable(job.func):
                            job.result = job.func(*job.args, **job.kwargs)
                            job.set_status(JobStatus.FINISHED)
                        else:
                            # If func is a string, we can't execute it in tests
                            job.set_status(JobStatus.FINISHED)
                    except Exception as e:
                        job.exc_info = str(e)
                        job.set_status(JobStatus.FAILED)
        return None

    def register_birth(self) -> None:
        """Register worker birth. For fakeredis, just set the birth date."""
        from datetime import datetime
        self.birth_date = datetime.now()

    def prepare_job_execution(self, job: Any, remove_from_intermediate_queue: bool = False) -> None:
        """Prepare job for execution. For fakeredis, set job status to STARTED and add to registry."""
        if hasattr(job, 'set_status'):
            job.set_status(JobStatus.STARTED)
        elif hasattr(job, 'status'):
            job.status = JobStatus.STARTED
        
        # Add to started registry
        if hasattr(job, 'origin'):
            started_registry = StartedJobRegistry(job.origin, connection=self.connection)
            started_registry.add(job)

    def prepare_execution(self, job: Any) -> None:
        """Alias for prepare_job_execution."""
        self.prepare_job_execution(job)

    def monitor_work_horse(self, job: Any, queue: Any) -> None:
        """Monitor work horse. For fakeredis, set job as failed and remove from started registry."""
        if hasattr(job, 'set_status'):
            job.set_status(JobStatus.FAILED)
        # Remove from started registry
        started_registry = StartedJobRegistry(queue.name, connection=queue.connection)
        started_registry.remove(job.id)
        # Add to failed registry
        failed_registry = FailedJobRegistry(queue.name, connection=queue.connection)
        failed_registry.add(job.id)

    @staticmethod
    def count(connection: Any = None, queue: Any = None) -> int:
        """Return the number of workers. For fakeredis, return the number of registered workers."""
        return len(_WORKERS)
    
    @staticmethod
    def all(connection: Any = None) -> List['Worker']:
        """Return all workers. For fakeredis, return all registered workers."""
        return list(_WORKERS.values())
    
    @staticmethod
    def find_by_key(key: str, connection: Any = None) -> Optional['Worker']:
        """Find a worker by key. For fakeredis, look up in the workers registry."""
        return _WORKERS.get(key)
    
    def queue_names(self) -> List[str]:
        """Return the names of queues this worker is listening to."""
        return [queue.name for queue in self.queues]
    
    def get_current_job(self) -> Optional['Job']:
        """Get the current job being processed by this worker."""
        return self._current_job
    
    def get_state(self) -> str:
        """Get the current state of the worker."""
        return self.state
    
    def set_state(self, state: str) -> None:
        """Set the state of the worker."""
        self.state = state

# Connection helpers

def get_connection(*args: Any, **kwargs: Any):  # noqa: D401
    """Return a fakeredis connection-compatible object."""
    return _redis_instance

def get_redis_connection(*args: Any, **kwargs: Any):
    return _redis_instance

# Settings-like constants used in places
QUEUES_MAP = {"default": 0}
QUEUES_LIST = ["default"]

# Utilities used by project

# RQ exceptions shim
class InvalidJobOperation(Exception):
    """Raised when an invalid operation is performed on a job."""
    pass

class NoSuchJobError(Exception):
    """Raised when a job does not exist."""
    pass

# RQ job status enum
class JobStatus:
    """Job status constants compatible with RQ."""
    QUEUED = 'queued'
    STARTED = 'started'
    FINISHED = 'finished'
    FAILED = 'failed'
    DEFERRED = 'deferred'
    SCHEDULED = 'scheduled'
    STOPPED = 'stopped'
    CANCELED = 'canceled'
    
    # Aliases for compatibility
    STATUS_QUEUED = 'queued'
    STATUS_STARTED = 'started'
    STATUS_FINISHED = 'finished'
    STATUS_FAILED = 'failed'
    STATUS_DEFERRED = 'deferred'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_STOPPED = 'stopped'
    STATUS_CANCELED = 'canceled'

# RQ Job shim
class Job:
    """Minimal Job shim for compatibility."""
    def __init__(self, id=None, connection=None, origin=None, func=None):
        from datetime import datetime
        self.id = id or uuid.uuid4().hex
        self.connection = connection
        self.origin = origin or 'default'
        self.status = JobStatus.QUEUED
        self.created_at = datetime.now()
        self.enqueued_at = None
        self.started_at = None
        self.ended_at = None
        self.result = None
        self.exc_info = None
        self.func = func
        # Get full qualified name for func_name
        if func:
            # Build full path: module.class.method()
            module = getattr(func, '__module__', '')
            if hasattr(func, '__qualname__'):
                qualname = func.__qualname__
            elif hasattr(func, '__name__'):
                qualname = func.__name__
            else:
                qualname = str(func)
            
            # Combine module and qualname, add () at the end
            if module:
                self.func_name = f"{module}.{qualname}()"
            else:
                self.func_name = f"{qualname}()"
        else:
            self.func_name = 'unknown'
        self.args = ()
        self.kwargs = {}
        self.serializer = None
        self._exc_info = None
        self._dependency_id = None
        
        # Additional attributes for serializer compatibility
        # Description should be without () for compatibility
        if func:
            module = getattr(func, '__module__', '')
            if hasattr(func, '__qualname__'):
                qualname = func.__qualname__
            elif hasattr(func, '__name__'):
                qualname = func.__name__
            else:
                qualname = str(func)
            if module:
                self.description = f"{module}.{qualname}"
            else:
                self.description = qualname
        else:
            self.description = 'unknown'
        self.timeout = -1  # No timeout for fakeredis
        self.result_ttl = -1  # No TTL for fakeredis
        self.worker_name = ''  # No worker for fakeredis
        self.meta = {}  # Empty meta dict
        self.last_heartbeat = ''  # No heartbeat for fakeredis

    def get_status(self):
        """Get job status."""
        return self.status

    def set_status(self, status):
        """Set job status."""
        self.status = status
        if status == JobStatus.QUEUED:
            from datetime import datetime
            self.enqueued_at = datetime.now()
        elif status == JobStatus.STARTED:
            from datetime import datetime
            self.started_at = datetime.now()
        elif status in (JobStatus.FINISHED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.CANCELED):
            from datetime import datetime
            self.ended_at = datetime.now()
    
    def get_position(self):
        """Get job position in queue. For fakeredis, return -1."""
        return -1

    @property
    def is_failed(self):
        """Check if job failed."""
        return self.status == JobStatus.FAILED
    
    @property
    def is_finished(self):
        """Check if job finished."""
        return self.status == JobStatus.FINISHED
    
    @property
    def is_queued(self):
        """Check if job is queued."""
        return self.status == JobStatus.QUEUED
    
    @property
    def is_started(self):
        """Check if job is started."""
        return self.status == JobStatus.STARTED
    
    @property
    def is_deferred(self):
        """Check if job is deferred."""
        return self.status == JobStatus.DEFERRED
    
    @property
    def is_canceled(self):
        """Check if job is canceled."""
        return self.status == JobStatus.CANCELED
    
    @property
    def is_scheduled(self):
        """Check if job is scheduled."""
        return self.status == JobStatus.SCHEDULED
    
    @property
    def is_stopped(self):
        """Check if job is stopped."""
        return self.status == JobStatus.STOPPED

    @staticmethod
    def fetch(job_id, connection=None):
        """Fetch a job by ID. For fakeredis, return a dummy job."""
        return Job(id=job_id, connection=connection)

    @staticmethod
    def exists(job_id, connection=None):
        """Check if job exists. For fakeredis, check all queues."""
        for queue in _QUEUES.values():
            if job_id in queue._jobs:
                return True
        return False

# Global registries storage
_REGISTRIES: Dict[str, Dict[str, 'BaseRegistry']] = {}

# RQ registry shims
class BaseRegistry:
    """Base registry shim."""
    def __init__(self, name='default', connection=None):
        self.name = name
        self.connection = connection
        # Use global storage for job IDs to ensure singleton behavior
        registry_type = self.__class__.__name__
        if registry_type not in _REGISTRIES:
            _REGISTRIES[registry_type] = {}
        if name not in _REGISTRIES[registry_type]:
            _REGISTRIES[registry_type][name] = {'job_ids': []}
        self._storage = _REGISTRIES[registry_type][name]

    def get_job_ids(self):
        return self._storage['job_ids']

    def add(self, job_or_id, ttl: int = -1):
        """Add a job ID to the registry. Accepts either job object or job ID."""
        # Handle both job object and job ID
        if hasattr(job_or_id, 'id'):
            job_id = job_or_id.id
        else:
            job_id = str(job_or_id)
        
        if job_id not in self._storage['job_ids']:
            self._storage['job_ids'].append(job_id)

    def remove(self, job_id: str):
        """Remove a job ID from the registry."""
        if job_id in self._storage['job_ids']:
            self._storage['job_ids'].remove(job_id)

    def __len__(self):
        return len(self._storage['job_ids'])

    def __contains__(self, job_id: str):
        return job_id in self._storage['job_ids']

class FailedJobRegistry(BaseRegistry):
    pass

class StartedJobRegistry(BaseRegistry):
    pass

class FinishedJobRegistry(BaseRegistry):
    pass

class DeferredJobRegistry(BaseRegistry):
    pass

class ScheduledJobRegistry(BaseRegistry):
    def get_scheduled_time(self, job):
        """Get scheduled time for a job."""
        return getattr(job, 'scheduled_at', None)

class CanceledJobRegistry(BaseRegistry):
    pass

# RQ timeout exception
class JobTimeoutException(Exception):
    """Raised when a job times out."""
    pass

# RQ worker registration functions
def clean_worker_registry(connection=None):
    """Clean worker registry. No-op for fakeredis."""
    pass

# Decorator replacement for @job (no-op pass-through)

def job(*dargs: Any, **dkwargs: Any):
    def _wrap(func):
        return func
    return _wrap
