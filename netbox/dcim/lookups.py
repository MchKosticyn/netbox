from dcim.utils import object_to_path_node
from django.db import connection
try:
    from django.contrib.postgres.fields.array import ArrayContains
except Exception:
    class ArrayContains:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, item):
            def _missing(*args, **kwargs):
                raise TypeError('ArrayContains lookup is only supported on PostgreSQL')

            return _missing


class PathContains(ArrayContains):

    def get_prep_lookup(self):
        self.rhs = [object_to_path_node(self.rhs)]
        return super().get_prep_lookup()

# Lazy import ContentType to avoid import-time ORM access
try:
    try:
try:
try:
    try:
        from django.contrib.contenttypes.models import ContentType
    except Exception:
        ContentType = None
    # TODO: Lazy-import ContentType to avoid importing ORM at module import time
except Exception:
    ContentType = None
# TODO: Lazy-import ContentType to avoid importing ORM at module import time
except Exception:
    ContentType = None
# TODO: Lazy-import ContentType to avoid importing ORM at module import time
    except Exception:
        ContentType = None
    # TODO: Lazy-import ContentType to avoid importing ORM at module import time
except Exception:
    ContentType = None

