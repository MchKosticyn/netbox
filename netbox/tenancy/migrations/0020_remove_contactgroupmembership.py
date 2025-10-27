from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenancy', '0019_contactgroup_comments_tenantgroup_comments'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Remove the "through" models from the M2M field
                migrations.AlterField(
                    model_name='contact',
                    name='groups',
                    field=models.ManyToManyField(
                        blank=True,
                        related_name='contacts',
                        related_query_name='contact',
                        to='tenancy.contactgroup'
                    ),
                ),
                # Remove the ContactGroupMembership model
                migrations.DeleteModel(
                    name='ContactGroupMembership',
                ),
            ],
            database_operations=[
                # Rename ContactGroupMembership table
                migrations.AlterModelTable(
                    name='ContactGroupMembership',
                    table='tenancy_contact_groups',
                ),
                # Rename the 'group' column (also renames its FK constraint)
                migrations.RenameField(
                    model_name='contactgroupmembership',
                    old_name='group',
                    new_name='contactgroup',
                ),
                # PostgreSQL-specific sequence/index/constraint renames skipped for sqlite
                migrations.RunPython(code=migrations.RunPython.noop),
                migrations.RunPython(code=migrations.RunPython.noop),
                migrations.RunPython(code=migrations.RunPython.noop),
                migrations.RunPython(code=migrations.RunPython.noop),
                migrations.RunPython(code=migrations.RunPython.noop),
                migrations.RunPython(code=migrations.RunPython.noop),
            ],
        ),
    ]
