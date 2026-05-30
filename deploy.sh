#!/bin/bash
# ─────────────────────────────────────────────
#  UTME SQUAD  –  Deployment Script
# ─────────────────────────────────────────────
set -e

echo "▶ Installing dependencies..."
pip install -r requirements.txt

echo "▶ Collecting static files..."
python manage.py collectstatic --noinput

echo "▶ Running migrations..."
python manage.py migrate

echo "▶ Setting up initial admin password..."
python manage.py shell << 'PYEOF'
from api.views import hash_password
from api.models import AppSettings
import os

admin_pw = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'admin123')
unlock_pw = os.environ.get('DEFAULT_UNLOCK_PASSWORD', 'UTME')

obj, created = AppSettings.objects.get_or_create(
    key='admin_password',
    defaults={'value': hash_password(admin_pw), 'description': 'Admin login password'}
)
if created:
    print(f"✓ Admin password set")
else:
    print(f"✓ Admin password already set (not changed)")

obj2, created2 = AppSettings.objects.get_or_create(
    key='unlock_password',
    defaults={'value': unlock_pw, 'description': 'Messaging unlock password'}
)
if created2:
    print(f"✓ Unlock password set")
else:
    print(f"✓ Unlock password already set (not changed)")
PYEOF

echo "✅ Deployment setup complete!"
echo ""
echo "Start server with:"
echo "  daphne -b 0.0.0.0 -p 8000 utme_squad.asgi:application"
