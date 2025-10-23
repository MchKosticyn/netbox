from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from utilities.data import ranges_to_string, string_to_ranges

from ..utils import parse_numeric_range


class SimpleArrayField(forms.Field):
    """A lightweight replacement for django.contrib.postgres.forms.SimpleArrayField.

    Accepts a base_field (a Django form field) to validate each list element.
    Value is represented as a Python list. Input may be a list or comma-separated string.
    """

    def __init__(self, base_field=None, *args, **kwargs):
        self.base_field = base_field or forms.CharField()
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value is None:
            return []
        if isinstance(value, str):
            if value.strip() == '':
                return []
            return [v.strip() for v in value.split(',')]
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def validate(self, value):
        super().validate(value)
        # Validate each item using base_field
        errors = []
        cleaned = []
        for item in value:
            try:
                cleaned_item = self.base_field.clean(item)
                cleaned.append(cleaned_item)
            except forms.ValidationError as e:
                errors.extend(e.error_list)
        if errors:
            raise forms.ValidationError(errors)
        return cleaned

__all__ = (
    'NumericArrayField',
    'NumericRangeArrayField',
)


class NumericArrayField(SimpleArrayField):

    def clean(self, value):
        if value and not self.to_python(value):
            raise forms.ValidationError(
                _("Invalid list ({value}). Must be numeric and ranges must be in ascending order.").format(value=value)
            )
        return super().clean(value)

    def to_python(self, value):
        if not value:
            return []
        if isinstance(value, str):
            value = ','.join([str(n) for n in parse_numeric_range(value)])
        return super().to_python(value)


class NumericRangeArrayField(forms.CharField):
    """
    A field which allows for array of numeric ranges:
      Example: 1-5,10,20-30
    """
    def __init__(self, *args, help_text='', **kwargs):
        if not help_text:
            help_text = mark_safe(
                _(
                    "Specify one or more individual numbers or numeric ranges separated by commas. Example: {example}"
                ).format(example="<code>1-5,10,20-30</code>")
            )
        super().__init__(*args, help_text=help_text, **kwargs)

    def clean(self, value):
        if value and not self.to_python(value):
            raise forms.ValidationError(
                _("Invalid ranges ({value}). Must be a range of integers in ascending order.").format(value=value)
            )
        return super().clean(value)

    def prepare_value(self, value):
        if isinstance(value, str):
            return value
        return ranges_to_string(value)

    def to_python(self, value):
        return string_to_ranges(value)
