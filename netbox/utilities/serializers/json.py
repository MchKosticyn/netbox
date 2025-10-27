from django.core.serializers.json import Deserializer, Serializer as Serializer_  # noqa: F401
from django.utils.encoding import is_protected_type
# ArrayField is represented as JSON in SQLite
ArrayField = dict  # sentinel used only for type checks in serializer

# NOTE: Module must contain both Serializer and Deserializer


class Serializer(Serializer_):
    """
    Custom extension of Django's JSON serializer to support ArrayFields (see
    https://code.djangoproject.com/ticket/33974).
    """
    def _value_from_field(self, obj, field):
        value = field.value_from_object(obj)

        # Handle ArrayFields of protected types
        if type(field) is ArrayField:
            if not value or is_protected_type(value[0]):
                return value

        return value if is_protected_type(value) else field.value_to_string(obj)
