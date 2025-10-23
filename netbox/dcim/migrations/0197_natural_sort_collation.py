from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('dcim', '0196_qinq_svlan'),
    ]

    operations = []  # Collation is Postgres-specific; no-op for SQLite

