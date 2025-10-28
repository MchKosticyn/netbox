#!/bin/bash

# NetBox Server Startup Script
# This script prepares and starts the NetBox server with SQLite and fakeredis

set -e  # Exit on error

echo "=== NetBox Server Startup ==="
echo ""

# Activate virtual environment
echo "1. Activating virtual environment..."
source .venv/bin/activate

# Remove old database if exists (optional, comment out if you want to keep data)
# echo "2. Removing old database..."
# rm -f netbox.db

# Run migrations
echo "2. Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "3. Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
echo "4. Creating superuser (if not exists)..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    u = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created: username=admin, password=admin')
else:
    print('Superuser already exists')
" 2>/dev/null || echo "Superuser creation skipped"

# Create API token for admin user
echo "5. Creating/retrieving API token..."
TOKEN=$(python manage.py shell -c "
from users.models import Token
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(username='admin')
t, created = Token.objects.get_or_create(user=u)
print(t.key)
" 2>/dev/null | tail -1)

echo ""
echo "=== Setup Complete ==="
echo ""
echo "API Token: $TOKEN"
echo ""
echo "Starting server on 127.0.0.1:8000..."
echo "Login credentials: username=admin, password=admin"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
python manage.py runserver 127.0.0.1:8000
