from __future__ import annotations
from typing import Any, Dict, Iterable, List
from utilities.fakeredis_shim import FakeQueue


def get_statistics(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Get RQ statistics. Returns a dict with workers, queues, and jobs info."""
    from .queues import get_queue
    from .settings import QUEUES_LIST, QUEUES_MAP
    from .workers import get_worker
    
    # Ignore run_maintenance_tasks parameter for fakeredis
    run_maintenance_tasks = kwargs.get('run_maintenance_tasks', False)
    
    queues_data = []
    for i, queue_config in enumerate(QUEUES_LIST):
        queue_name = queue_config['name'] if isinstance(queue_config, dict) else queue_config
        queue = get_queue(queue_name)
        
        # Get additional queue statistics
        from utilities.fakeredis_shim import (
            FinishedJobRegistry, FailedJobRegistry, StartedJobRegistry,
            DeferredJobRegistry, ScheduledJobRegistry, CanceledJobRegistry
        )
        
        finished_registry = FinishedJobRegistry(queue_name, connection=queue.connection)
        failed_registry = FailedJobRegistry(queue_name, connection=queue.connection)
        started_registry = StartedJobRegistry(queue_name, connection=queue.connection)
        deferred_registry = DeferredJobRegistry(queue_name, connection=queue.connection)
        scheduled_registry = ScheduledJobRegistry(queue_name, connection=queue.connection)
        canceled_registry = CanceledJobRegistry(queue_name, connection=queue.connection)
        
        queues_data.append({
            'name': queue_name,
            'jobs': queue.count,
            'index': QUEUES_MAP.get(queue_name, i),
            'oldest_job_timestamp': '',  # Empty string instead of None for serializer compatibility
            'scheduler_pid': '',  # Empty string for fakeredis
            'workers': 0,  # No workers for fakeredis
            'finished_jobs': len(finished_registry),
            'failed_jobs': len(failed_registry),
            'started_jobs': len(started_registry),
            'deferred_jobs': len(deferred_registry),
            'scheduled_jobs': len(scheduled_registry),
            'canceled_jobs': len(canceled_registry),
        })
    
    return {
        "workers": 1,  # Fake worker count
        "queues": queues_data,
        "jobs": sum(q['jobs'] for q in queues_data),
    }


def get_jobs(queue: FakeQueue, job_ids: Iterable[str], registry: Any) -> List[Any]:
    """Get jobs by IDs from queue."""
    jobs = []
    for job_id in job_ids:
        job = queue.fetch_job(job_id)
        if job:
            jobs.append(job)
    return jobs


def stop_jobs(queue: FakeQueue, job_id: str):
    return [0]
