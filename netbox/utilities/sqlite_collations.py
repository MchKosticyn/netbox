from django.db.backends.signals import connection_created
import re
from netaddr import IPNetwork, IPAddress

def _register_on_connection(conn):
    if getattr(conn, 'vendor', None) != 'sqlite':
        return
    try:
        # Collation 'C' (binary compare)
        def collate_c(a, b):
            return (a > b) - (a < b)
        try:
            conn.create_collation('C', collate_c)
        except Exception:
            pass
        # Collation 'natural_sort'
        _chunk_re = re.compile(r'(\d+|\D+)')
        def natkey(s):
            parts = _chunk_re.findall(s or '')
            out = []
            for p in parts:
                if p.isdigit():
                    out.append((0, int(p)))
                else:
                    out.append((1, p.lower()))
            return out
        def collate_natural(a, b):
            ka, kb = natkey(a), natkey(b)
            return (ka > kb) - (ka < kb)
        try:
            conn.create_collation('natural_sort', collate_natural)
        except Exception:
            pass

        # Register SQLite functions for IP/CIDR operations
        def inet_contains(parent, child):
            try:
                p = IPNetwork(parent)
                c = IPNetwork(child)
                return int((c in p) and (c != p))  # strict containment
            except Exception:
                return 0
        def inet_contains_or_equals(parent, child):
            try:
                p = IPNetwork(parent)
                c = IPNetwork(child)
                return int((c in p) or (c == p))
            except Exception:
                return 0
        def inet_contained(child, parent):
            try:
                c = IPNetwork(child)
                p = IPNetwork(parent)
                return int((c in p) and (c != p))  # strict containment
            except Exception:
                return 0
        def inet_host(address):
            try:
                return str(IPAddress(str(address).split('/')[0]))
            except Exception:
                return None
        def host(address):
            # Alias for INET_HOST to satisfy Transform(function='HOST')
            return inet_host(address)
        def inet_cast(value):
            """Return a lexicographically sortable key for IP address strings.

            For IPv4: '4:' + zero-padded 3-digit octets (e.g., 192.168.0.1 -> '4:192168000001')
            For IPv6: '6:' + 32 hex digits (no colons), uppercase (e.g., full expanded form)
            Accepts inputs with or without mask; mask is ignored for comparison key.
            """
            try:
                s = str(value) if value is not None else ''
                host = s.split('/')[0]
                ip = IPAddress(host)
                if ip.version == 4:
                    parts = [f"{int(o):03d}" for o in str(ip).split('.')]
                    return '4:' + ''.join(parts)
                else:
                    # Expand to 32 hex digits
                    hexdigits = ip.format(0).replace(':', '')  # full, no zero compression
                    # Some netaddr versions: format(0) yields full form; ensure length 32
                    hexdigits = hexdigits.zfill(32)
                    return '6:' + hexdigits.upper()
            except Exception:
                return None
        def family(address):
            try:
                ip = IPAddress(str(address).split('/')[0])
                return int(ip.version)
            except Exception:
                return None
        def masklen(address):
            try:
                s = str(address)
                if '/' in s:
                    return int(IPNetwork(s).prefixlen)
                # No mask provided: return host-max mask length
                ip = IPAddress(s)
                return 32 if ip.version == 4 else 128
            except Exception:
                return None
        try:
            conn.connection.create_function('INET_CONTAINS', 2, inet_contains)
            conn.connection.create_function('INET_CONTAINS_OR_EQUALS', 2, inet_contains_or_equals)
            conn.connection.create_function('INET_CONTAINED', 2, inet_contained)
            conn.connection.create_function('INET_HOST', 1, inet_host)
            # Additional generic functions used by Transforms/Managers
            conn.connection.create_function('HOST', 1, host)
            conn.connection.create_function('INET', 1, inet_cast)
            conn.connection.create_function('FAMILY', 1, family)
            conn.connection.create_function('MASKLEN', 1, masklen)

            # Provide REGEXP operator support on SQLite
            def _regexp(pattern, value):
                try:
                    return 1 if re.search(pattern, value or '') else 0
                except Exception:
                    return 0
            # SQLite looks up a scalar function named by the operator (case-insensitive)
            conn.connection.create_function('REGEXP', 2, _regexp)
            conn.connection.create_function('regexp', 2, _regexp)

            # Range array containment for JSONField: RANGE_ARRAY_CONTAINS(json_array, scalar)
            def range_array_contains(json_array, scalar):
                import json as _json
                try:
                    ranges = _json.loads(json_array) if isinstance(json_array, str) else json_array
                except Exception:
                    return 0
                try:
                    v = int(scalar)
                except Exception:
                    return 0
                if not ranges:
                    return 0
                for r in ranges:
                    try:
                        lower = int(r.get('lower'))
                        upper = int(r.get('upper'))
                        bounds = str(r.get('bounds', '[)'))
                        lower_inc = bounds.startswith('[')
                        upper_inc = bounds.endswith(']')
                        lower_ok = (v >= lower) if lower_inc else (v > lower)
                        upper_ok = (v <= upper) if upper_inc else (v < upper)
                        if lower_ok and upper_ok:
                            return 1
                    except Exception:
                        continue
                return 0
            conn.connection.create_function('RANGE_ARRAY_CONTAINS', 2, range_array_contains)

            # Array contains for JSON arrays: ARRAY_CONTAINS(json_array, scalar)
            def array_contains(json_array, scalar):
                import json as _json
                try:
                    arr = _json.loads(json_array) if isinstance(json_array, str) else json_array
                except Exception:
                    return 0
                try:
                    v = int(scalar)
                except Exception:
                    # attempt string compare fallback
                    v = scalar
                try:
                    return 1 if v in arr else 0
                except Exception:
                    return 0
            conn.connection.create_function('ARRAY_CONTAINS', 2, array_contains)

            # Choices contains for JSON choice arrays [[value,label], ...]
            def choices_contains_value(json_array, scalar):
                import json as _json
                try:
                    arr = _json.loads(json_array) if isinstance(json_array, str) else json_array
                except Exception:
                    return 0
                try:
                    target = scalar
                except Exception:
                    target = scalar
                try:
                    for item in arr or []:
                        # Allow flat scalar lists: ['A','B',...]
                        if not isinstance(item, (list, tuple, dict)):
                            if item == target:
                                return 1
                            continue
                        # Support [value, label] pairs
                        if isinstance(item, (list, tuple)) and item:
                            if item[0] == target:
                                return 1
                            continue
                        # Also support {'value': ..., 'label': ...}
                        if isinstance(item, dict) and 'value' in item and item.get('value') == target:
                            return 1
                    return 0
                except Exception:
                    return 0
            conn.connection.create_function('CHOICES_CONTAINS_VALUE', 2, choices_contains_value)

            # Lexicographic date compare for ISO dates: returns -1, 0, 1
            def date_cmp(a, b):
                try:
                    if a is None or b is None:
                        return None  # propagate NULL to avoid matching comparisons
                    sa = str(a)
                    sb = str(b)
                    if sa > sb:
                        return 1
                    if sa < sb:
                        return -1
                    return 0
                except Exception:
                    return None
            conn.connection.create_function('DATE_CMP', 2, date_cmp)
        except Exception:
            pass
    except Exception:
        pass

def _on_created(sender, connection, **kwargs):
    _register_on_connection(connection)

# Connect signal to register collations for future SQLite connections
connection_created.connect(_on_created)
