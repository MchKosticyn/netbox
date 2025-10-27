from django.db import models

from netbox.models import NetBoxModel


class DummyModel(models.Model):
    name = models.CharField(
        max_length=20
    )
    number = models.IntegerField(
        default=100
    )

    class Meta:
        app_label = 'dummy_plugin'  # Make model constructible outside INSTALLED_APPS for tests
        ordering = ['name']


class DummyNetBoxModel(NetBoxModel):
    class Meta:
        app_label = 'dummy_plugin'  # Same as above to satisfy model base registration
