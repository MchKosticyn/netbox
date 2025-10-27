# Minimal settings shim for django_rq
QUEUES_LIST = [
    {"name": "default", "connection_config": {}},
    {"name": "high", "connection_config": {}},
    {"name": "low", "connection_config": {}},
]
QUEUES_MAP = {"default": 0, "high": 1, "low": 2}
