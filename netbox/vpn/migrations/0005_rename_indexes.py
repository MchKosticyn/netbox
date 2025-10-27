from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('vpn', '0004_alter_ikepolicy_mode'),
    ]

    operations = [
        # Rename vpn_l2vpn constraints
        # PostgreSQL-specific constraint rename skipped for sqlite
        migrations.RunPython(code=migrations.RunPython.noop),
        # Rename ipam_l2vpn_* sequences
        # PostgreSQL-specific sequence renames skipped for sqlite
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        # Rename ipam_l2vpn_* indexes
        # PostgreSQL-specific index renames skipped for sqlite
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        # Rename vpn_l2vpntermination constraints
        # PostgreSQL-specific constraint renames skipped for sqlite
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        # Rename ipam_l2vpn_termination_* sequences
        # PostgreSQL-specific sequence/index renames skipped for sqlite
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
        migrations.RunPython(code=migrations.RunPython.noop),
    ]
