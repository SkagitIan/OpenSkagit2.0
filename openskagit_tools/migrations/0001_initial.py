import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='McpAccessRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('email', models.EmailField(db_index=True, max_length=254)),
                ('organization', models.CharField(blank=True, max_length=160)),
                ('agent_client', models.CharField(blank=True, max_length=120)),
                ('intended_use', models.TextField()),
                ('expected_volume', models.CharField(choices=[('low', 'Occasional'), ('medium', 'Regular'), ('high', 'High volume')], default='low', max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('declined', 'Declined')], db_index=True, default='pending', max_length=20)),
                ('agreed_to_terms', models.BooleanField(default=False)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=300)),
                ('admin_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='McpOAuthClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160)),
                ('client_id', models.CharField(db_index=True, max_length=100, unique=True)),
                ('encrypted_client_secret', models.TextField()),
                ('redirect_uris', models.JSONField(default=list)),
                ('scope', models.CharField(default='openskagit.read', max_length=200)),
                ('active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('access_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='oauth_clients', to='openskagit_tools.mcpaccessrequest')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='McpOAuthAuthorizationCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_digest', models.CharField(db_index=True, max_length=64, unique=True)),
                ('scopes', models.JSONField(default=list)),
                ('redirect_uri', models.TextField()),
                ('redirect_uri_provided_explicitly', models.BooleanField(default=True)),
                ('code_challenge', models.CharField(max_length=180)),
                ('subject', models.CharField(blank=True, max_length=200)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='authorization_codes', to='openskagit_tools.mcpoauthclient')),
            ],
        ),
        migrations.CreateModel(
            name='McpOAuthGrant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token_digest', models.CharField(db_index=True, max_length=64, unique=True)),
                ('refresh_token_digest', models.CharField(db_index=True, max_length=64, unique=True)),
                ('scopes', models.JSONField(default=list)),
                ('subject', models.CharField(blank=True, max_length=200)),
                ('access_expires_at', models.DateTimeField(db_index=True)),
                ('refresh_expires_at', models.DateTimeField(db_index=True)),
                ('active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grants', to='openskagit_tools.mcpoauthclient')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
