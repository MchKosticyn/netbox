from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0007_objectpermission_update_object_types'),
    ]

    operations = [
        # NOTE: SQLite-compatible migration.
        # We perform real DB operations so that the implicit through tables
        # (users_group_object_permissions, users_user_object_permissions)
        # are created on a fresh database. Previously this was done via
        # SeparateDatabaseAndState with DB no-ops (meant for PostgreSQL table renames),
        # which leaves no through tables on SQLite and causes OperationalError.

        # Flip M2M assignments for ObjectPermission to Groups
        migrations.RemoveField(
            model_name='objectpermission',
            name='groups',
        ),
        migrations.AddField(
            model_name='group',
            name='object_permissions',
            field=models.ManyToManyField(blank=True, related_name='groups', to='users.objectpermission'),
        ),

        # Flip M2M assignments for ObjectPermission to Users
        migrations.RemoveField(
            model_name='objectpermission',
            name='users',
        ),
        migrations.AddField(
            model_name='user',
            name='object_permissions',
            field=models.ManyToManyField(blank=True, related_name='users', to='users.objectpermission'),
        ),
    ]
