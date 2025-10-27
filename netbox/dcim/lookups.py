from dcim.utils import object_to_path_node
from django.db import connection
# Remove PostgreSQL dependency: define a no-op lookup that errors on use (SQLite does not support ArrayContains)
class ArrayContains:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, item):
        def _missing(*args, **kwargs):
            raise TypeError('ArrayContains lookup is not supported on SQLite')
        return _missing


from django.db.models import Lookup

class PathContains(Lookup):
    lookup_name = 'path_contains'

    def as_sql(self, compiler, connection):
        # SQLite JSON path containment is not supported; raise clear error if used.
        raise TypeError('PathContains lookup is not supported on SQLite JSONField')


