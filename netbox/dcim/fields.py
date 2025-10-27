from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _
from netaddr import AddrFormatError, EUI, eui64_unix_expanded, mac_unix_expanded

from .lookups import PathContains

# SQLite-only codebase: do not import or use PostgreSQL ArrayField

__all__ = (
    'MACAddressField',
    'PathField',
    'WWNField',
)


# Keep default netaddr dialects (lowercase, colon-separated) to mirror PostgreSQL canonical output.

#
# Fields
#

class MACAddressField(models.Field):
    description = 'PostgreSQL MAC Address field'

    def python_type(self):
        return EUI

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def get_internal_type(self):
        return 'CharField'

    def to_python(self, value):
        if value is None:
            return value
        if type(value) is str:
            value = value.replace(' ', '')
        try:
            # Use lowercase canonical formatting to match PostgreSQL macaddr text representation
            return EUI(value, version=48, dialect=mac_unix_expanded)
        except AddrFormatError:
            raise ValidationError(_("Invalid MAC address format: {value}").format(value=value))

    def db_type(self, connection):
        return 'macaddr'

    def get_prep_value(self, value):
        if not value:
            return None
        return str(self.to_python(value))


class WWNField(models.Field):
    description = 'World Wide Name field'

    def python_type(self):
        return EUI

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def get_internal_type(self):
        return 'CharField'

    def to_python(self, value):
        if value is None:
            return value
        try:
            # Use lowercase canonical formatting for consistency with PostgreSQL macaddr8
            return EUI(value, version=64, dialect=eui64_unix_expanded)
        except AddrFormatError:
            raise ValidationError(_("Invalid WWN format: {value}").format(value=value))

    def db_type(self, connection):
        return 'macaddr8'

    def get_prep_value(self, value):
        if not value:
            return None
        return str(self.to_python(value))


class PathField(models.JSONField):
    """
    SQLite-compatible JSONField storing a list of object identifiers.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault('default', list)
        super().__init__(**kwargs)

# Register a placeholder lookup name to avoid import-time registration errors
PathField.register_lookup(PathContains)
