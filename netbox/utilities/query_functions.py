from django.db.models import Func

__all__ = (
    'CollateAsChar',
    'EmptyGroupByJSONBAgg',
)


class CollateAsChar(Func):
    """
    Disregard localization by collating a field as a plain character string. Helpful for ensuring predictable ordering.
    """
    function = 'C'
    template = '(%(expressions)s) COLLATE "%(function)s"'


class EmptyGroupByJSONBAgg(Func):
    """
    Fallback aggregation for SQLite: act as an identity function in SQL rendering to avoid GROUP BY usage.
    This does not provide true JSON aggregation but preserves query syntax for testing under SQLite.

    TODO: This is a lightweight shim for SQLite compatibility. Replace with Postgres JSONBAgg
    implementation when running against PostgreSQL.
    """
    contains_aggregate = False
    function = ''
    template = '%(expressions)s'
