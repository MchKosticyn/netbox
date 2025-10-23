from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0007_objectpermission_update_object_types'),
    ]

    operations = [
        # Flip M2M assignments for ObjectPermission to Groups
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='objectpermission',
                    name='groups',
                ),
                migrations.AddField(
                    model_name='group',
                    name='object_permissions',
                    field=models.ManyToManyField(blank=True, related_name='groups', to='users.objectpermission'),
                ),
            ],
            database_operations=[
                # PostgreSQL-specific table/index/constraint renames skipped for sqlite
                migrations.RunPython(code=migrations.RunPython.noop),
            ],
        ),
        # Flip M2M assignments for ObjectPermission to Users
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name='objectpermission',
                    name='users',
                ),
                migrations.AddField(
                    model_name='user',
                    name='object_permissions',
                    field=models.ManyToManyField(blank=True, related_name='users', to='users.objectpermission'),
                ),
            ],
            database_operations=[
                # PostgreSQL-specific renames skipped on sqlite
                migrations.RunPython(code=migrations.RunPython.noop),
            ],
        ),
    ]
