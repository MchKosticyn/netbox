from django.db import models
from django.db.models import Func, F

__all__ = (
    'CollateAsChar',
    'CollateNatural',
    'EmptyGroupByJSONBAgg',
    'JSONExtract',
)


class CollateAsChar(Func):
    """
    SQLite-only: collate as plain character string using BINARY (no PostgreSQL support in this project).
    """
    def __init__(self, expression, **extra):
        # Allow passing a field name as a string
        if isinstance(expression, str):
            expression = F(expression)
        super().__init__(expression, **extra)

    def as_sql(self, compiler, connection, **extra_context):
        self.template = '(%(expressions)s) COLLATE BINARY'
        return super().as_sql(compiler, connection, **extra_context)


class CollateNatural(Func):
    """
    SQLite-only: apply custom 'natural_sort' collation registered at runtime.
    Ensure registration on the current connection to avoid 'no such collation' errors during tests.
    """
    def __init__(self, expression, **extra):
        # Allow passing a field name as a string
        if isinstance(expression, str):
            expression = F(expression)
        super().__init__(expression, **extra)

    def as_sql(self, compiler, connection, **extra_context):
        # If backend is not SQLite, fall back to binary collation to avoid errors
        if getattr(connection, 'vendor', None) == 'sqlite':
            # Ensure the collation exists on this exact connection. Register inline if missing.
            try:
                import re as _re
                _chunk_re = _re.compile(r'(\d+|\D+)')
                def _natkey(s):
                    parts = _chunk_re.findall(s or '')
                    key = []
                    for p in parts:
                        if p.isdigit():
                            key.append((0, int(p)))
                        else:
                            key.append((1, p.lower()))
                    return key
                def _collate_natural(a, b):
                    ka, kb = _natkey(a), _natkey(b)
                    return (ka > kb) - (ka < kb)
                try:
                    connection.create_collation('natural_sort', _collate_natural)
                except Exception:
                    pass
                try:
                    raw = getattr(connection, 'connection', None)
                    if raw is not None:
                        raw.create_collation('natural_sort', _collate_natural)
                except Exception:
                    pass
            except Exception:
                # Best-effort; fallback to binary if registration failed
                self.template = '(%(expressions)s) COLLATE BINARY'
                return super().as_sql(compiler, connection, **extra_context)
            collation = 'natural_sort'
        else:
            collation = 'BINARY'
        self.template = f'(%(expressions)s) COLLATE {collation}'
        return super().as_sql(compiler, connection, **extra_context)


class JSONExtract(Func):
    """
    SQLite helper: json_extract(expression, '$.path') with a correctly quoted JSON path.
    Falls back to function json_extract on other backends as a no-op wrapper.
    """
    function = 'json_extract'
    # Ensure Django treats the result as text by default to avoid mixed JSONField/CharField resolution errors
    output_field = models.TextField()

    def __init__(self, expression, path, output_field=None, **extra):
        # Allow passing field name as string
        if isinstance(expression, str):
            expression = F(expression)
        self.json_path = path
        # Allow overriding, but default to TextField
        if output_field is None:
            output_field = self.output_field
        super().__init__(expression, output_field=output_field, **extra)

    def as_sql(self, compiler, connection, **extra_context):
        if getattr(connection, 'vendor', None) == 'sqlite':
            self.template = "json_extract(%(expressions)s, '%(json_path)s')"
            extra_context.update({'json_path': self.json_path})
        else:
            self.template = '%(function)s(%(expressions)s)'
        return super().as_sql(compiler, connection, **extra_context)


class EmptyGroupByJSONBAgg(Func):
    """
    SQLite fallback aggregation: use JSON1 json_group_array() to aggregate rows into a JSON array.
    - If called with one expression (data), aggregates raw values.
    - If called with three expressions (weight, name, data), aggregates JSON objects {'w': weight, 'n': name, 'd': data}
      to preserve ordering metadata for post-processing.
    On non-SQLite backends, acts as a pass-through placeholder returning the expression.
    """
    contains_aggregate = True
    output_field = models.TextField()

    def as_sql(self, compiler, connection, **extra_context):
        if getattr(connection, 'vendor', None) == 'sqlite':
            function = 'json_group_array'
            if len(self.source_expressions) == 3:
                # Compile each expression separately and build json_object('w', w, 'n', n, 'd', d)
                sqls = []
                params = []
                for expr in self.source_expressions:
                    s, p = compiler.compile(expr)
                    sqls.append(s)
                    params.extend(p)
                inner_sql = f"json_object('w', {sqls[0]}, 'n', {sqls[1]}, 'd', {sqls[2]})"
                sql = f"{function}({inner_sql})"
                return sql, params
            else:
                # Default: aggregate the single expression as-is
                self.function = function
                self.template = '%(function)s(%(expressions)s)'
                return super().as_sql(compiler, connection, **extra_context)
        # Non-SQLite: pass-through
        self.template = '%(expressions)s'
        return super().as_sql(compiler, connection, **extra_context)
