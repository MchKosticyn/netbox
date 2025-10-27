import decimal
import re
from itertools import count, groupby

# NumericRange is a Postgres-specific type; provide a lightweight replacement for SQLite
# TODO: This is a compatibility shim used for SQLite-based tests. If running on PostgreSQL,
# consider replacing this with the native range type or a more feature-complete implementation.
class NumericRange:
    def __init__(self, lower, upper, bounds='[)'):
        self.lower = int(lower)
        self.upper = int(upper)
        self.lower_inc = bounds.startswith('[')
        self.upper_inc = bounds.endswith(']')
        self.bounds = bounds

    def __repr__(self):
        return f"NumericRange({self.lower}, {self.upper}, bounds='{self.bounds}')"

    def __eq__(self, other):
        if not isinstance(other, NumericRange):
            return NotImplemented
        return (
            self.lower == other.lower and
            self.upper == other.upper and
            self.lower_inc == other.lower_inc and
            self.upper_inc == other.upper_inc
        )


def _coerce_range_like(r):
    """
    Normalize a range-like item (NumericRange or dict from JSONField or any object with
    lower/upper[/bounds|/lower_inc,/upper_inc]) to a tuple:
    (lower:int, upper:int, lower_inc:bool, upper_inc:bool)
    """
    # Direct support for our shim class
    if isinstance(r, NumericRange):
        return int(r.lower), int(r.upper), bool(r.lower_inc), bool(r.upper_inc)
    # Dict from JSONField
    if isinstance(r, dict):
        lower = int(r.get('lower')) if r.get('lower') is not None else 0
        upper = int(r.get('upper')) if r.get('upper') is not None else 0
        bounds = str(r.get('bounds', '[)'))
        lower_inc = bounds.startswith('[')
        upper_inc = bounds.endswith(']')
        return lower, upper, lower_inc, upper_inc
    # Duck-typing: any object with lower/upper
    if hasattr(r, 'lower') and hasattr(r, 'upper'):
        lower = int(getattr(r, 'lower'))
        upper = int(getattr(r, 'upper'))
        if hasattr(r, 'lower_inc') and hasattr(r, 'upper_inc'):
            lower_inc = bool(getattr(r, 'lower_inc'))
            upper_inc = bool(getattr(r, 'upper_inc'))
        else:
            bounds = str(getattr(r, 'bounds', '[)'))
            lower_inc = bounds.startswith('[')
            upper_inc = bounds.endswith(']')
        return lower, upper, lower_inc, upper_inc
    raise TypeError(f'Unsupported range-like type: {type(r)!r}')

__all__ = (
    'array_to_ranges',
    'array_to_string',
    'check_ranges_overlap',
    'deepmerge',
    'drange',
    'flatten_dict',
    'ranges_to_string',
    'ranges_to_string_list',
    'shallow_compare_dict',
    'string_to_ranges',
)


#
# Dictionary utilities
#

def deepmerge(original, new):
    """
    Deep merge two dictionaries (new into original) and return a new dict.
    Be tolerant to non-dict input: if `new` is not a dict, return a copy of `original` unchanged.
    """
    # Guard: only merge dicts; anything else is ignored to keep callers resilient to bad data
    if type(new) is not dict:
        try:
            return dict(original)
        except Exception:
            return {}
    merged = dict(original)
    for key, val in new.items():
        if key in original and isinstance(original[key], dict) and val and isinstance(val, dict):
            merged[key] = deepmerge(original[key], val)
        else:
            merged[key] = val
    return merged


def flatten_dict(d, prefix='', separator='.'):
    """
    Flatten nested dictionaries into a single level by joining key names with a separator.

    :param d: The dictionary to be flattened
    :param prefix: Initial prefix (if any)
    :param separator: The character to use when concatenating key names
    """
    ret = {}
    for k, v in d.items():
        key = separator.join([prefix, k]) if prefix else k
        if type(v) is dict:
            ret.update(flatten_dict(v, prefix=key, separator=separator))
        else:
            ret[key] = v
    return ret


def shallow_compare_dict(source_dict, destination_dict, exclude=tuple()):
    """
    Return a new dictionary of the different keys. The values of `destination_dict` are returned. Only the equality of
    the first layer of keys/values is checked. `exclude` is a list or tuple of keys to be ignored.
    """
    difference = {}

    for key, value in destination_dict.items():
        if key in exclude:
            continue
        if source_dict.get(key) != value:
            difference[key] = value

    return difference


#
# Array utilities
#

def array_to_ranges(array):
    """
    Convert an arbitrary array of integers to a list of consecutive values. Nonconsecutive values are returned as
    single-item tuples.

    Accepts a scalar (int/str) or an iterable; gracefully handles None.

    Example:
        [0, 1, 2, 10, 14, 15, 16] => [(0, 2), (10,), (14, 16)]
    """
    # Normalize input to a list of ints
    values: list[int]
    if array is None:
        values = []
    elif isinstance(array, (list, tuple, set)):
        values = [int(v) for v in array]
    elif isinstance(array, str):
        # Try to split by comma/whitespace; fall back to single int
        parts = [p for p in re.split(r"[\s,]+", array) if p]
        if len(parts) > 1:
            values = [int(p) for p in parts]
        else:
            values = [int(array)]
    else:
        # Scalar number or any other type convertible to int
        try:
            values = [int(array)]
        except Exception:
            values = []

    if not values:
        return []

    # Sort and group consecutive values
    group = (
        list(x) for _, x in groupby(sorted(values), lambda x, c=count(): next(c) - x)
    )
    return [
        (g[0], g[-1])[:len(g)] for g in group
    ]


def array_to_string(array):
    """
    Generate an efficient, human-friendly string from a set of integers. Intended for use with ArrayField.

    Example:
        [0, 1, 2, 10, 14, 15, 16] => "0-2, 10, 14-16"
    """
    ret = []
    ranges = array_to_ranges(array)
    for value in ranges:
        if len(value) == 1:
            ret.append(str(value[0]))
        else:
            ret.append(f'{value[0]}-{value[1]}')
    return ', '.join(ret)


#
# Range utilities
#

def drange(start, end, step=decimal.Decimal(1)):
    """
    Decimal-compatible implementation of Python's range()
    """
    start, end, step = decimal.Decimal(start), decimal.Decimal(end), decimal.Decimal(step)
    if start < end:
        while start < end:
            yield start
            start += step
    else:
        while start > end:
            yield start
            start += step


def check_ranges_overlap(ranges):
    """
    Check for overlap in an iterable of range-like objects using half-open semantics.

    Accepts either NumericRange instances or dicts with keys lower/upper/bounds
    (as produced by JSONField under SQLite). Treat each range as
    [lower_inclusive, upper_exclusive). Two ranges overlap if
    prev_upper_exclusive > curr_lower_inclusive after sorting by lower.
    """
    if not ranges:
        return False

    # Coerce to comparable tuples without mutating originals
    coerced = [
        _coerce_range_like(r) for r in ranges
    ]

    def lower_inclusive(t):
        lower, _upper, lower_inc, _upper_inc = t
        return lower if lower_inc else lower + 1

    def upper_exclusive(t):
        _lower, upper, _lower_inc, upper_inc = t
        return upper + 1 if upper_inc else upper

    coerced.sort(key=lambda t: (lower_inclusive(t), t[1]))

    prev_upper_ex = upper_exclusive(coerced[0])
    for t in coerced[1:]:
        curr_lower_in = lower_inclusive(t)
        if prev_upper_ex > curr_lower_in:
            return True
        # track farthest upper to catch nested overlaps
        t_upper_ex = upper_exclusive(t)
        if t_upper_ex > prev_upper_ex:
            prev_upper_ex = t_upper_ex
    return False


def ranges_to_string_list(ranges):
    """
    Convert numeric ranges to a list of display strings.

    Accepts NumericRange objects or dicts with lower/upper/bounds.
    Each range is rendered as "lower-upper" or "lower" (for singletons).
    Bounds are normalized to inclusive values using ``lower_inc``/``upper_inc``.
    This underpins ``ranges_to_string()``, which joins the result with commas.

    Example:
        [NumericRange(1, 6), NumericRange(8, 9), NumericRange(10, 13)] => ["1-5", "8", "10-12"]
    """
    if not ranges:
        return []

    output: list[str] = []
    for r in ranges:
        lower, upper, lower_inc, upper_inc = _coerce_range_like(r)
        # Compute inclusive bounds regardless of how the DB range is stored.
        lower_inc_v = lower if lower_inc else lower + 1
        upper_inc_v = upper if upper_inc else upper - 1
        output.append(f"{lower_inc_v}-{upper_inc_v}" if lower_inc_v != upper_inc_v else str(lower_inc_v))
    return output


def ranges_to_string(ranges):
    """
    Converts a list of ranges into a string representation.

    This function takes a list of range objects and produces a string
    representation of those ranges. Each range is represented as a
    hyphen-separated pair of lower and upper bounds, with inclusive or
    exclusive bounds adjusted accordingly. If the lower and upper bounds
    of a range are the same, only the single value is added to the string.
    Intended for use with ArrayField.

    Example:
        [NumericRange(1, 5), NumericRange(8, 9), NumericRange(10, 12)] => "1-5,8,10-12"
    """
    if not ranges:
        return ''
    return ','.join(ranges_to_string_list(ranges))


def string_to_ranges(value):
    """
    Converts a string representation of numeric ranges into a list of NumericRange objects.

    This function parses a string containing numeric values and ranges separated by commas (e.g.,
    "1-5,8,10-12") and converts it into a list of NumericRange objects.
    In the case of a single integer, it is treated as a range where the start and end
    are equal. The returned ranges are represented as half-open intervals [lower, upper).
    Intended for use with ArrayField.

    Example:
        "1-5,8,10-12" => [NumericRange(1, 6), NumericRange(8, 9), NumericRange(10, 13)]
    """
    if not value:
        return None
    value.replace(' ', '')  # Remove whitespace
    values = []
    for data in value.split(','):
        dash_range = data.strip().split('-')
        if len(dash_range) == 1 and str(dash_range[0]).isdigit():
            # Single integer value; expand to a range
            lower = dash_range[0]
            upper = dash_range[0]
        elif len(dash_range) == 2 and str(dash_range[0]).isdigit() and str(dash_range[1]).isdigit():
            # The range has two values and both are valid integers
            lower = dash_range[0]
            upper = dash_range[1]
        else:
            return None
        values.append(NumericRange(int(lower), int(upper) + 1, bounds='[)'))
    return values
