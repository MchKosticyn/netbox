import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_user_remove_is_staff'),
    ]

    operations = [
        # Rename the original key field to "plaintext"
        migrations.RenameField(
            model_name='token',
            old_name='key',
            new_name='plaintext',
        ),
        migrations.RunSQL(
            sql="ALTER INDEX IF EXISTS users_token_key_820deccd_like RENAME TO users_token_plaintext_46c6f315_like",
        ),
        migrations.RunSQL(
            sql="ALTER INDEX IF EXISTS users_token_key_key RENAME TO users_token_plaintext_key",
        ),
        # Make plaintext (formerly key) nullable for v2 tokens
        migrations.AlterField(
            model_name='token',
            name='plaintext',
            field=models.CharField(
                max_length=40,
                unique=True,
                blank=True,
                null=True,
                validators=[django.core.validators.MinLengthValidator(40)]
            ),
        ),
        # Add version field to distinguish v1 and v2 tokens
        migrations.AddField(
            model_name='token',
            name='version',
            field=models.PositiveSmallIntegerField(default=1),  # Mark all existing Tokens as v1
            preserve_default=False,
        ),
        # Change the default version for new tokens to v2
        migrations.AlterField(
            model_name='token',
            name='version',
            field=models.PositiveSmallIntegerField(default=2),
        ),
        # Add new key, pepper, and hmac_digest fields for v2 tokens
        migrations.AddField(
            model_name='token',
            name='key',
            field=models.CharField(blank=True, max_length=16, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='token',
            name='pepper',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='token',
            name='hmac_digest',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
