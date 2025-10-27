from django.db import migrations, models
# Replaced GistIndex with plain Index for SQLite compatibility


class Migration(migrations.Migration):
# NOTE: Migration adjusted for SQLite — opclasses/GistIndex removed
    atomic = False


    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('dcim', '0210_macaddress_ordering'),
        ('extras', '0129_fix_script_paths'),
        ('ipam', '0081_remove_service_device_virtual_machine_add_parent_gfk_index'),
        ('tenancy', '0020_remove_contactgroupmembership'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='prefix',
            index=models.Index(fields=['prefix'], name='ipam_prefix_idx'),
        ),
    ]
