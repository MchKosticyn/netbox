from django.db import migrations, models

import utilities.json


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_remove_redundant_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='log_entries',
            # Use JSONField on SQLite to store list of log entries
            field=models.JSONField(
                decoder=utilities.json.JobLogDecoder,
                encoder=utilities.json.DjangoJSONEncoder if hasattr(utilities.json, 'DjangoJSONEncoder') else None,
                blank=True,
                null=True,
                default=list,
            ),
        ),
    ]
