from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0011_concrete_objecttype'),
    ]

    operations = [
        # Django admin UI was removed in NetBox v4.0
        # Older installations may still have the old `django_admin_log` table in place
        # Drop the obsolete table if it exists. This is a no-op on fresh or already-clean DBs.
        # PostgreSQL-specific cleanup (noop on sqlite)
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
    ]
