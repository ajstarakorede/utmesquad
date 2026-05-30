#!/usr/bin/env python
"""
Setup script for UTME SQUAD platform.
Run this after installing requirements to initialize the database and create default data.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'utme_squad.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup():
    print("=" * 60)
    print("UTME SQUAD - Setup Script")
    print("=" * 60)
    
    # Check if Django is installed
    try:
        import django
        print(f"\nDjango version: {django.__version__}")
    except ImportError:
        print("\nError: Django is not installed.")
        print("Please run: pip install -r requirements.txt")
        return False
    
    # Setup Django
    django.setup()
    
    # Run migrations
    print("\n[1/4] Running database migrations...")
    from django.core.management import call_command
    call_command('makemigrations', verbosity=0)
    call_command('migrate', verbosity=0)
    print("Migrations complete!")
    
    # Create default settings
    print("\n[2/4] Creating default settings...")
    from api.models import AppSettings, ChatGroup, SubjectGroup
    import hashlib
    
    # Admin password (default: admin123)
    hashed_admin = hashlib.sha256(("admin123" + "UTME_SQUAD_SALT_v2").encode()).hexdigest()
    AppSettings.objects.get_or_create(
        key='admin_password',
        defaults={'value': hashed_admin, 'description': 'Admin login password'}
    )
    print("Admin password set (default: admin123)")
    
    # Unlock password (default: UTME)
    AppSettings.objects.get_or_create(
        key='unlock_password',
        defaults={'value': 'UTME', 'description': 'Password to unlock messaging feature'}
    )
    print("Unlock password set (default: UTME)")
    
    # Create default groups
    print("\n[3/4] Creating default chat groups...")
    
    # General UTME SQUAD group
    general_group, created = ChatGroup.objects.get_or_create(
        name='utme_squad',
        defaults={
            'display_name': 'UTME SQUAD',
            'group_type': 'general',
            'description': 'General group for all UTME candidates',
            'icon': 'fa-users'
        }
    )
    if created:
        print("Created 'UTME SQUAD' general group")
    
    # Subject groups
    subjects = [
        ('English', 'English Study Group'),
        ('Mathematics', 'Mathematics Study Group'),
        ('Physics', 'Physics Study Group'),
        ('Chemistry', 'Chemistry Study Group'),
        ('Biology', 'Biology Study Group'),
        ('Government', 'Government Study Group'),
        ('Literature', 'Literature Study Group'),
        ('CRS', 'CRS Study Group'),
        ('IRS', 'IRS Study Group'),
        ('Economics', 'Economics Study Group'),
        ('Commerce', 'Commerce Study Group'),
    ]
    
    for subject_name, display_name in subjects:
        group, created = ChatGroup.objects.get_or_create(
            name=f'subject_{subject_name.lower()}',
            defaults={
                'display_name': display_name,
                'group_type': 'subject',
                'subject_name': subject_name,
                'description': f'Discussion group for {subject_name}',
                'icon': 'fa-book'
            }
        )
        if created:
            print(f"Created '{display_name}' group")
        
        SubjectGroup.objects.get_or_create(
            subject_name=subject_name,
            defaults={
                'display_name': display_name,
                'chat_group': group
            }
        )
    
    # Collect static files
    print("\n[4/4] Collecting static files...")
    call_command('collectstatic', '--noinput', verbosity=0)
    print("Static files collected!")
    
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("\nDefault Credentials:")
    print("  Admin Password: admin123")
    print("  Unlock Password: UTME")
    print("  Candidate Password: candidate123")
    print("\nTo start the server, run:")
    print("  python manage.py runserver")
    print("\nThen visit:")
    print("  http://127.0.0.1:8000/ - Candidate Login")
    print("  http://127.0.0.1:8000/admin/ - Admin Login")
    print("=" * 60)
    
    return True

if __name__ == '__main__':
    setup()
