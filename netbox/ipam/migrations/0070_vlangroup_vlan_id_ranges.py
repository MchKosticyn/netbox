from django.db import migrations, models
# This migration stores vid_ranges as JSON for SQLite
import ipam.models.vlans


def set_vid_ranges(apps, schema_editor):
    # Ensure ContentType is accessed via apps in migration runtime to avoid import-time ORM access
    # Use apps.get_model('contenttypes', 'ContentType') inside this function if ContentType is required
    VLANGroup = apps.get_model('ipam', 'VLANGroup')
    db_alias = schema_editor.connection.alias

    for group in VLANGroup.objects.using(db_alias).all():
        # Use a JSON-serializable representation for sqlite compatibility
        group.vid_ranges = [[group.min_vid, group.max_vid]]
        group._total_vlan_ids = group.max_vid - group.min_vid + 1
        group.save()
    """
    Convert the min_vid & max_vid fields to a range in the new vid_ranges ArrayField.
    For sqlite, store as a simple list [min, max] to avoid Postgres-specific NumericRange.
    """
    VLANGroup = apps.get_model('ipam', 'VLANGroup')
    db_alias = schema_editor.connection.alias

    for group in VLANGroup.objects.using(db_alias).all():
        # Use a JSON-serializable representation for sqlite compatibility
        group.vid_ranges = [[group.min_vid, group.max_vid]]
        group._total_vlan_ids = group.max_vid - group.min_vid + 1
        group.save()


class Migration(migrations.Migration):
    dependencies = [
        ('ipam', '0069_gfk_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='vlangroup',
            name='vid_ranges',
            # Postgres Range/Array field replaced with JSONField for sqlite compatibility
            field=models.JSONField(default=list, serialize=False),
        ),
        migrations.AddField(
            model_name='vlangroup',
            name='_total_vlan_ids',
            field=models.PositiveBigIntegerField(default=4094),
        ),
        migrations.RunPython(code=set_vid_ranges, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='vlangroup',
            name='max_vid',
        ),
        migrations.RemoveField(
            model_name='vlangroup',
            name='min_vid',
        ),
    ]
