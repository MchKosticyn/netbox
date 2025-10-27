from django.apps import AppConfig
from django.conf import settings
from django.core.cache import cache
from django.db import models, connection
from django.db.migrations.operations import AlterModelOptions
from django.utils.translation import gettext as _
from django.db.backends.signals import connection_created
import re

from core.events import *
from netbox.events import EventType, EVENT_TYPE_KIND_DANGER, EVENT_TYPE_KIND_SUCCESS, EVENT_TYPE_KIND_WARNING
from utilities.migration import custom_deconstruct

# Ignore verbose_name & verbose_name_plural Meta options when calculating model migrations
AlterModelOptions.ALTER_OPTION_KEYS.remove('verbose_name')
AlterModelOptions.ALTER_OPTION_KEYS.remove('verbose_name_plural')

# Use our custom destructor to ignore certain attributes when calculating field migrations
models.Field.deconstruct = custom_deconstruct


class CoreConfig(AppConfig):
    name = "core"

    def _register_sqlite_collations(self):
        """Register missing collations for SQLite test/dev runs."""
        if connection.vendor != 'sqlite':
            return
        try:
            # 'C' collation: simple binary compare similar to Postgres 'C'
            def collate_c(a, b):
                return (a > b) - (a < b)
            try:
                connection.create_collation('C', collate_c)
            except Exception:
                pass

            # 'natural_sort' collation: compare by chunks of digits/text case-insensitive
            _chunk_re = re.compile(r"(\d+|\D+)")
            def natkey(s):
                parts = _chunk_re.findall(s or '')
                key = []
                for p in parts:
                    if p.isdigit():
                        key.append((0, int(p)))
                    else:
                        key.append((1, p.lower()))
                return key
            def collate_natural(a, b):
                ka, kb = natkey(a), natkey(b)
                return (ka > kb) - (ka < kb)
            try:
                connection.create_collation('natural_sort', collate_natural)
            except Exception:
                pass
        except Exception:
            # Never block startup on collation registration
            pass

    def ready(self):
        from core.api import schema  # noqa: F401
        from core.checks import check_duplicate_indexes  # noqa: F401
        from netbox.models.features import register_models
        from . import data_backends, events, search  # noqa: F401
        from netbox import context_managers  # noqa: F401
        # Ensure SQLite UDFs and extra collations (INET/JSON helpers) are registered
        # by importing the registration module which hooks connection_created
        from utilities import sqlite_collations  # noqa: F401

        # Ensure collations are registered on each new SQLite connection (applies to migrations/tests)
        def _on_connection_created(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                try:
                    self._register_sqlite_collations()
                except Exception:
                    pass
        connection_created.connect(_on_connection_created)

        # Register models
        register_models(*self.get_models())

        # Register core events
        EventType(OBJECT_CREATED, _('Object created')).register()
        EventType(OBJECT_UPDATED, _('Object updated')).register()
        EventType(OBJECT_DELETED, _('Object deleted'), destructive=True).register()
        EventType(JOB_STARTED, _('Job started')).register()
        EventType(JOB_COMPLETED, _('Job completed'), kind=EVENT_TYPE_KIND_SUCCESS).register()
        EventType(JOB_FAILED, _('Job failed'), kind=EVENT_TYPE_KIND_WARNING).register()
        EventType(JOB_ERRORED, _('Job errored'), kind=EVENT_TYPE_KIND_DANGER).register()

        # Also attempt immediate registration for the current connection
        self._register_sqlite_collations()

        # Clear Redis cache on startup in development mode
        if settings.DEBUG:
            try:
                cache.clear()
            except Exception:
                pass
