from django.http import Http404
from django.utils.translation import gettext_lazy as _
# Replaced django_rq with in-memory shim for tests/dev
from utilities.fakeredis_shim import get_redis_connection  # type: ignore
# Use our django_rq shim APIs
from django_rq import get_queue
from django_rq.settings import QUEUES_LIST, QUEUES_MAP
from django_rq.utils import get_jobs, stop_jobs

# RQ classes are not used with shim; provide lightweight aliases
class RQJobStatus:
    STARTED = "started"
    DEFERRED = "deferred"
    FINISHED = "finished"
    FAILED = "failed"
    SCHEDULED = "scheduled"

class NoSuchJobError(Exception):
    pass

class RQ_Job:
    @staticmethod
    def fetch(job_id, connection=None, serializer=None):
        """Fetch a job from any queue."""
        # Try to find job in all queues
        for queue_name in ['default', 'high', 'low']:
            queue = get_queue(queue_name)
            job = queue.fetch_job(job_id)
            if job:
                return job
        raise NoSuchJobError(f"Job {job_id} not found")
    
    @staticmethod
    def exists(job_id, connection=None):
        """Check if job exists in any queue."""
        try:
            RQ_Job.fetch(job_id, connection)
            return True
        except NoSuchJobError:
            return False

# Import registries from fakeredis_shim
from utilities.fakeredis_shim import (
    DeferredJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
    FailedJobRegistry,
)

# Add get_scheduled_time method to ScheduledJobRegistry if not present
if not hasattr(ScheduledJobRegistry, 'get_scheduled_time'):
    def _get_scheduled_time(self, job):
        return getattr(job, 'scheduled_at', None)
    ScheduledJobRegistry.get_scheduled_time = _get_scheduled_time

def requeue_job(*args, **kwargs):
    return None

__all__ = (
    'delete_rq_job',
    'enqueue_rq_job',
    'get_rq_jobs',
    'get_rq_jobs_from_status',
    'requeue_rq_job',
    'stop_rq_job',
)


def get_rq_jobs():
    """
    Return a list of all RQ jobs.
    """
    jobs = set()

    for queue in QUEUES_LIST:
        queue = get_queue(queue['name'])
        jobs.update(queue.get_jobs())

    return list(jobs)


def get_rq_jobs_from_status(queue, status):
    """
    Return the RQ jobs with the given status.
    """
    jobs = []

    try:
        registry_cls = {
            RQJobStatus.STARTED: StartedJobRegistry,
            RQJobStatus.DEFERRED: DeferredJobRegistry,
            RQJobStatus.FINISHED: FinishedJobRegistry,
            RQJobStatus.FAILED: FailedJobRegistry,
            RQJobStatus.SCHEDULED: ScheduledJobRegistry,
        }[status]
    except KeyError:
        raise Http404
    registry = registry_cls(queue.name, queue.connection)

    job_ids = registry.get_job_ids()
    if status != RQJobStatus.DEFERRED:
        jobs = get_jobs(queue, job_ids, registry)
    else:
        # Deferred jobs require special handling
        for job_id in job_ids:
            try:
                jobs.append(RQ_Job.fetch(job_id, connection=queue.connection, serializer=queue.serializer))
            except NoSuchJobError:
                pass

    if jobs and status == RQJobStatus.SCHEDULED:
        for job in jobs:
            job.scheduled_at = registry.get_scheduled_time(job)

    return jobs


def delete_rq_job(job_id):
    """
    Delete the specified RQ job.
    """
    try:
        job = RQ_Job.fetch(job_id)
    except NoSuchJobError:
        raise Http404(_("Job {job_id} not found").format(job_id=job_id))

    # Remove job from its queue
    for queue_name in ['default', 'high', 'low']:
        queue = get_queue(queue_name)
        if job_id in queue._jobs:
            del queue._jobs[job_id]
            break
    
    return None


def requeue_rq_job(job_id):
    """
    Requeue the specified RQ job.
    """
    try:
        job = RQ_Job.fetch(job_id)
    except NoSuchJobError:
        raise Http404(_("Job {id} not found.").format(id=job_id))

    # Set job status to QUEUED
    job.set_status('queued')
    return None


def enqueue_rq_job(job_id):
    """
    Enqueue the specified RQ job.
    """
    try:
        job = RQ_Job.fetch(job_id)
    except NoSuchJobError:
        raise Http404(_("Job {id} not found.").format(id=job_id))

    # Set job status to QUEUED
    job.set_status('queued')
    return None


def stop_rq_job(job_id):
    """
    Stop the specified RQ job.
    """
    try:
        job = RQ_Job.fetch(job_id)
    except NoSuchJobError:
        raise Http404(_("Job {job_id} not found").format(job_id=job_id))

    # Set job status to STOPPED
    job.set_status('stopped')
    return [job_id]
