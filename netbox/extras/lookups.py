from django.db.models import CharField, JSONField, Lookup
from django.db.models.fields.json import KeyTextTransform
from django.db import connection
# Pure SQLite: no Postgres field types
PostgresArrayField = None
PostgresRangeField = None
_HAS_PG = False
# Avoid importing ContentType here; import it locally where actually needed

from .fields import CachedValueField


class JSONContains(Lookup):
    """
    Emulate JSONField __contains on SQLite using JSON1.
    Supported cases:
      - dict RHS: all key/value pairs must be present in JSON object
      - list/tuple RHS: all elements must be present in JSON array (AND semantics)
      - scalar RHS: element must be present in JSON array (EXISTS)
    Nested structures are not supported.
    """
    lookup_name = 'contains'

    def as_sql(self, compiler, connection):
        if connection.vendor != 'sqlite':
            raise TypeError('JSONField contains shim only for sqlite in this build')

        lhs_sql, lhs_params = compiler.compile(self.lhs)
        rhs_obj = self.rhs
        params = list(lhs_params)

        if isinstance(rhs_obj, dict):
            conditions = []
            for k, v in rhs_obj.items():
                conditions.append(f"json_extract({lhs_sql}, '$.{k}') = ?")
                params.append(v)
            sql = ' AND '.join(conditions) if conditions else '1'
            return sql, params

        # Normalize list/tuple -> list
        if isinstance(rhs_obj, (list, tuple)):
            elements = list(rhs_obj)
            conditions = []
            for _ in elements:
                conditions.append(f"EXISTS (SELECT 1 FROM json_each({lhs_sql}) AS e WHERE e.value = ?)")
            params.extend(elements)
            sql = ' AND '.join(conditions) if conditions else '1'
            return sql, params

        # Scalar: check membership in array
        conditions = [f"EXISTS (SELECT 1 FROM json_each({lhs_sql}) AS e WHERE e.value = ?)"]
        params.append(rhs_obj)
        return ' AND '.join(conditions), params


class RangeContains(Lookup):
    """
    Filter ArrayField(RangeField) columns where ANY element-range contains the scalar RHS.

    SQLite implementation expects JSON array of objects with shape
    {"lower": int, "upper": int, "bounds": "[)"|"[]"|"(]"|"()"} stored in a JSONField.

    Usage (ORM):
        Model.objects.filter(<json_range_array_field>__range_contains=<scalar>)
    """

    lookup_name = 'range_contains'

    def as_sql(self, compiler, connection):
        if connection.vendor == 'sqlite':
            # Delegate to SQLite UDF implemented in utilities/sqlite_collations.py
            # RANGE_ARRAY_CONTAINS(<json array>, <scalar>) -> 1/0
            lhs_sql, lhs_params = self.process_lhs(compiler, connection)
            rhs_sql, rhs_params = self.process_rhs(compiler, connection)
            sql = f"RANGE_ARRAY_CONTAINS({lhs_sql}, {rhs_sql})"
            params = lhs_params + rhs_params
            return sql, params

        # For other backends (e.g., Postgres), leave unimplemented in this build
        raise TypeError('range_contains lookup is not supported for backend: %s' % connection.vendor)


class Empty(Lookup):
    """
    Filter on whether a string is empty.
    """
    lookup_name = 'empty'
    prepare_rhs = False

    def as_sql(self, compiler, connection):
        sql, params = compiler.compile(self.lhs)
        if self.rhs:
            return f"CAST(LENGTH({sql}) AS BOOLEAN) IS NOT TRUE", params
        else:
            return f"CAST(LENGTH({sql}) AS BOOLEAN) IS TRUE", params


class JSONEmpty(Lookup):
    """
    Support "empty" lookups for JSONField keys.

    A key is considered empty if it is "", null, or does not exist.
    """
    lookup_name = 'empty'

    def as_sql(self, compiler, connection):
        # self.lhs.lhs is the parent expression (could be a JSONField or another KeyTransform)
        # Rebuild the expression using KeyTextTransform to guarantee ->> (text)
        text_expr = KeyTextTransform(self.lhs.key_name, self.lhs.lhs)
        lhs_sql, lhs_params = compiler.compile(text_expr)

        value = self.rhs
        if value not in (True, False):
            raise ValueError("The 'empty' lookup only accepts True or False.")

        condition = '' if value else 'NOT '
        sql = f"(NULLIF({lhs_sql}, '') IS {condition}NULL)"

        return sql, lhs_params


class NetHost(Lookup):
    """
    SQLite-safe: compare only host portions using HOST() UDF (see utilities/sqlite_collations.py).
    """
    lookup_name = 'net_host'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        # On SQLite we register HOST() as alias of INET_HOST(); avoid CAST AS INET (PostgreSQL-specific)
        return 'HOST(%s) = HOST(%s)' % (lhs, rhs), params


class NetContainsOrEquals(Lookup):
    """
    SQLite-safe: use INET_CONTAINS_OR_EQUALS() UDF; replaces PostgreSQL operator >>=.
    """
    lookup_name = 'net_contains_or_equals'

    def as_sql(self, qn, connection):
        lhs, lhs_params = self.process_lhs(qn, connection)
        rhs, rhs_params = self.process_rhs(qn, connection)
        params = lhs_params + rhs_params
        return 'INET_CONTAINS_OR_EQUALS(%s, %s)' % (lhs, rhs), params


# No registration for Postgres-only lookups under SQLite
CharField.register_lookup(Empty)
JSONField.register_lookup(JSONEmpty)
# Register SQLite JSON range containment lookup
JSONField.register_lookup(RangeContains)
# Register JSON contains shim for SQLite
JSONField.register_lookup(JSONContains)
CachedValueField.register_lookup(NetHost)
CachedValueField.register_lookup(NetContainsOrEquals)
