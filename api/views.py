"""
API Views for UTME SQUAD Platform.
"""

import json
import hashlib
import os
import io
import base64
import uuid
from datetime import datetime
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, Count, Avg

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas

from .models import (
    Candidate, Message, ChatGroup, GroupMessage, VoiceMessage,
    UnlockRecord, AppSettings, Notification, SubjectGroup, CandidateFile
)


# ============== UTILITY FUNCTIONS ==============

def hash_password(password):
    """Hash password using PBKDF2-SHA256 (Django's make_password)."""
    from django.contrib.auth.hashers import make_password as _make_pw
    return _make_pw(password)

def verify_password(plain, stored):
    """Timing-safe password check supporting PBKDF2 and legacy SHA256."""
    import hmac
    from django.contrib.auth.hashers import check_password as _check_pw
    # Legacy SHA256 format: 64-char lowercase hex string
    if len(stored) == 64 and all(c in '0123456789abcdef' for c in stored):
        legacy_hash = hashlib.sha256((plain + "UTME_SQUAD_SALT_v2").encode()).hexdigest()
        return hmac.compare_digest(legacy_hash, stored)
    return _check_pw(plain, stored)


def generate_token():
    """Generate a unique session token."""
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()



ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
ALLOWED_AUDIO_TYPES = {'audio/webm', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav'}
MAX_PHOTO_SIZE = 2 * 1024 * 1024   # 2 MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB

def validate_upload(uploaded_file, allowed_types, max_size):
    """Return (ok, error_message)."""
    if uploaded_file.size > max_size:
        return False, f"File too large (max {max_size // (1024*1024)} MB)"
    content_type = uploaded_file.content_type or ''
    if content_type not in allowed_types:
        return False, f"Invalid file type: {content_type}"
    return True, None

def api_login_required(view_func):
    """Decorator to check if admin is logged in."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        admin_session = request.session.get('admin_logged_in')
        if not admin_session:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def candidate_login_required(view_func):
    """Decorator to check if candidate is logged in."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        candidate_id = request.session.get('candidate_id')
        if not candidate_id:
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def get_unlock_password_value():
    """Get the current unlock password from settings."""
    password = AppSettings.get_value('unlock_password')
    if not password:
        password = 'UTME'
        AppSettings.set_value('unlock_password', password, 'Password to unlock messaging feature')
    return password


def get_admin_password_value():
    """Get the current admin password from settings."""
    password = AppSettings.get_value('admin_password')
    if not password:
        password = hash_password('admin123')
        AppSettings.set_value('admin_password', password, 'Admin login password')
    return password


def create_notification(user_type, user_identifier, message, notification_type='system', link=''):
    """Create a notification for a user."""
    Notification.objects.create(
        user_type=user_type,
        user_identifier=user_identifier,
        message=message,
        notification_type=notification_type,
        link=link
    )


def ensure_default_groups():
    """Create default groups if they don't exist."""
    # General UTME SQUAD group
    general_group, _ = ChatGroup.objects.get_or_create(
        name='utme_squad',
        defaults={
            'display_name': 'UTME SQUAD',
            'group_type': 'general',
            'description': 'General group for all UTME candidates',
            'icon': 'fa-users'
        }
    )
    
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
        group, _ = ChatGroup.objects.get_or_create(
            name=f'subject_{subject_name.lower()}',
            defaults={
                'display_name': display_name,
                'group_type': 'subject',
                'subject_name': subject_name,
                'description': f'Discussion group for {subject_name}',
                'icon': 'fa-book'
            }
        )
        
        SubjectGroup.objects.get_or_create(
            subject_name=subject_name,
            defaults={
                'display_name': display_name,
                'chat_group': group
            }
        )
    
    return general_group


# ============== PAGE VIEWS ==============

@ensure_csrf_cookie
def admin_login(request):
    """Admin login page."""
    if request.session.get('admin_logged_in'):
        return redirect('admin_dashboard')
    return render(request, 'admin/login.html')


@ensure_csrf_cookie
def admin_dashboard(request):
    """Admin dashboard page."""
    if not request.session.get('admin_logged_in'):
        return redirect('admin_login')
    
    ensure_default_groups()
    
    context = {
        'total_candidates': Candidate.objects.count(),
        'active_candidates': Candidate.objects.filter(online=True).count(),
        'total_messages': Message.objects.count() + GroupMessage.objects.count(),
        'suspended_count': Candidate.objects.filter(is_active=False).count(),
        'messaging_paused_count': Candidate.objects.filter(messaging_paused=True).count(),
        'unlocked_count': Candidate.objects.filter(can_message=True).count(),
        'unlock_password': get_unlock_password_value(),
    }
    return render(request, 'admin/dashboard.html', context)


def admin_logout(request):
    """Admin logout."""
    request.session.flush()
    return redirect('admin_login')


@ensure_csrf_cookie
def candidate_login(request):
    """Candidate login page."""
    if request.session.get('candidate_id'):
        return redirect('candidate_dashboard')
    return render(request, 'candidate/login.html')


@ensure_csrf_cookie
def candidate_dashboard(request):
    """Candidate dashboard page."""
    candidate_id = request.session.get('candidate_id')
    if not candidate_id:
        return redirect('candidate_login')
    
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        request.session.flush()
        return redirect('candidate_login')
    
    if not candidate.is_active:
        request.session.flush()
        return render(request, 'candidate/login.html', {'error': 'Your account has been suspended. Contact the administrator.'})
    
    # Get groups the candidate can see
    ensure_default_groups()
    
    all_groups = ChatGroup.objects.filter(is_active=True)
    candidate_groups = []
    
    for group in all_groups:
        if group.group_type == 'general':
            candidate_groups.append(group)
        elif group.group_type == 'subject' and group.subject_name:
            if group.subject_name in candidate.subjects:
                candidate_groups.append(group)
    
    # Get unread notifications
    notifications = Notification.objects.filter(
        user_type='candidate',
        user_identifier=candidate.reg_number,
        is_read=False
    ).order_by('-created_at')[:10]
    
    context = {
        'candidate': candidate,
        'groups': candidate_groups,
        'notifications': notifications,
        'can_message': candidate.can_message and not candidate.messaging_paused,
        'messaging_paused': candidate.messaging_paused,
        'is_unlocked': candidate.can_message,
    }
    return render(request, 'candidate/dashboard.html', context)


def candidate_logout(request):
    """Candidate logout."""
    candidate_id = request.session.get('candidate_id')
    if candidate_id:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            candidate.online = False
            candidate.save()
        except Candidate.DoesNotExist:
            pass
    request.session.flush()
    return redirect('candidate_login')


def unlock_messaging(request):
    """Unlock messaging for a candidate."""
    candidate_id = request.session.get('candidate_id')
    if not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)
    
    if request.method == 'POST':
        password = request.POST.get('password', '').strip()
        
        if not password:
            return JsonResponse({'error': 'Please enter the password'}, status=400)
        
        correct_password = get_unlock_password_value()
        
        if password == correct_password:
            candidate.can_message = True
            candidate.save()
            
            # Record the unlock
            UnlockRecord.objects.create(
                candidate=candidate,
                password_used=password,
                ip_address=get_client_ip(request)
            )
            
            # Notify admin
            create_notification(
                'admin', 'admin',
                f'{candidate.name} ({candidate.reg_number}) has unlocked premium messaging.',
                'unlock'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Messaging unlocked! You can now message other users.'
            })
        else:
            return JsonResponse({'error': 'Incorrect password'}, status=400)
    
    return JsonResponse({'error': 'Invalid method'}, status=405)


def get_client_ip(request):
    """Get client IP address."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ============== API VIEWS ==============

@csrf_exempt
@require_http_methods(['POST'])
def api_admin_login(request):
    """API endpoint for admin login."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    password = data.get('password', '')
    
    if not password:
        return JsonResponse({'error': 'Password is required'}, status=400)
    
    # Server-side rate limiting: max 10 attempts per IP per 5 minutes
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown')).split(',')[0].strip()
    rate_key = f'admin_login_fail:{client_ip}'
    fail_count = cache.get(rate_key, 0)
    if fail_count >= 10:
        return JsonResponse({'error': 'Too many failed attempts. Try again in 5 minutes.'}, status=429)

    admin_password = get_admin_password_value()

    if verify_password(password, admin_password):
        request.session['admin_logged_in'] = True
        request.session['user_type'] = 'admin'
        request.session['user_name'] = 'Administrator'
        
        return JsonResponse({
            'success': True,
            'token': generate_token(),
            'user': {
                'type': 'admin',
                'name': 'Administrator',
            }
        })
    
    return JsonResponse({'error': 'Invalid password'}, status=401)


@require_http_methods(['POST'])
def api_admin_logout(request):
    """API endpoint for admin logout."""
    request.session.flush()
    return JsonResponse({'success': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_candidate_login(request):
    """API endpoint for candidate login."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    reg_number = data.get('reg_number', '').strip().upper()
    password = data.get('password', '').strip()
    
    if not reg_number:
        return JsonResponse({'error': 'Registration number is required'}, status=400)
    
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Registration number not found'}, status=404)
    
    if not candidate.is_active:
        return JsonResponse({'error': 'Your account has been suspended. Contact the administrator.'}, status=403)
    
    # Always require password — never allow login without one
    if not password:
        return JsonResponse({'error': 'Password is required'}, status=400)
    if not verify_password(password, candidate.password):
        return JsonResponse({'error': 'Invalid password'}, status=401)
    
    # Update candidate status
    candidate.online = True
    candidate.login_count += 1
    candidate.save()
    
    request.session['candidate_id'] = candidate.id
    request.session['candidate_reg'] = candidate.reg_number
    request.session['user_type'] = 'candidate'
    request.session['user_name'] = candidate.name
    
    return JsonResponse({
        'success': True,
        'token': generate_token(),
        'candidate': {
            'id': candidate.id,
            'name': candidate.name,
            'reg_number': candidate.reg_number,
            'email': candidate.email,
            'phone': candidate.phone,
            'photo': candidate.photo_url,
            'subjects': candidate.subjects,
            'can_message': candidate.can_message,
            'messaging_paused': candidate.messaging_paused,
        }
    })


@require_http_methods(['POST'])
def api_candidate_logout(request):
    """API endpoint for candidate logout."""
    candidate_id = request.session.get('candidate_id')
    if candidate_id:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            candidate.online = False
            candidate.save()
        except Candidate.DoesNotExist:
            pass
    request.session.flush()
    return JsonResponse({'success': True})


# ============== CANDIDATE MANAGEMENT ==============

@api_login_required
def candidates_list(request):
    """Get all candidates."""
    candidates = Candidate.objects.all().order_by('-created_at')
    data = []
    for c in candidates:
        data.append({
            'id': c.id,
            'name': c.name,
            'reg_number': c.reg_number,
            'email': c.email,
            'phone': c.phone,
            'photo': c.photo_url,
            'subjects': c.subjects,
            'is_active': c.is_active,
            'online': c.online,
            'can_message': c.can_message,
            'messaging_paused': c.messaging_paused,
            'exams_taken': c.exams_taken,
            'avg_score': c.avg_score,
            'created_at': c.created_at.isoformat(),
            'last_active': c.last_active.isoformat(),
        })
    return JsonResponse({'candidates': data})


@csrf_exempt
@api_login_required
def register_candidate(request):
    """Register a new candidate."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    name = request.POST.get('name', '').strip()
    reg_number = request.POST.get('reg_number', '').strip().upper()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    subjects_json = request.POST.get('subjects', '["English"]')
    password = request.POST.get('password', '').strip()
    
    if not name or not reg_number:
        return JsonResponse({'error': 'Name and registration number are required'}, status=400)
    
    # Check if reg_number exists
    if Candidate.objects.filter(reg_number=reg_number).exists():
        return JsonResponse({'error': 'Registration number already exists'}, status=400)
    
    # Handle photo upload with type validation
    photo = request.FILES.get('photo')
    if photo:
        ok, err = validate_upload(photo, ALLOWED_IMAGE_TYPES, MAX_PHOTO_SIZE)
        if not ok:
            return JsonResponse({'error': f'Photo upload rejected: {err}'}, status=400)

    if not password:
        import secrets, string
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
    plain_password = password  # save before hashing for PDF
    
    try:
        subjects = json.loads(subjects_json)
    except:
        subjects = ['English']
    
    candidate = Candidate.objects.create(
        reg_number=reg_number,
        name=name,
        email=email,
        phone=phone,
        password=hash_password(password),  # stored hashed, never plaintext
        subjects=subjects,
    )
    
    if photo:
        candidate.photo = photo
        candidate.save()
    
    # Generate PDF (best-effort — don't fail registration if PDF fails)
    try:
        generate_candidate_pdf_buffer(candidate)
    except Exception as e:
        print(f"PDF generation error (non-fatal): {e}")
    
    # Create notification
    create_notification(
        'admin', 'admin',
        f'New candidate registered: {name} ({reg_number})',
        'system'
    )
    
    return JsonResponse({
        'success': True,
        'candidate': {
            'id': candidate.id,
            'name': candidate.name,
            'reg_number': candidate.reg_number,
            'photo': candidate.photo_url,
            'subjects': candidate.subjects,
            'password': plain_password,  # returned once; stored as hash
        }
    })


@api_login_required
def candidate_detail(request, reg_number):
    """Get a single candidate's details."""
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)
    
    return JsonResponse({
        'candidate': {
            'id': candidate.id,
            'name': candidate.name,
            'reg_number': candidate.reg_number,
            'email': candidate.email,
            'phone': candidate.phone,
            'photo': candidate.photo_url,
            'subjects': candidate.subjects,
            'is_active': candidate.is_active,
            'online': candidate.online,
            'can_message': candidate.can_message,
            'messaging_paused': candidate.messaging_paused,
            'exams_taken': candidate.exams_taken,
            'avg_score': candidate.avg_score,
            'created_at': candidate.created_at.isoformat(),
            'last_active': candidate.last_active.isoformat(),
        }
    })


@api_login_required
def delete_candidate(request, reg_number):
    """Delete a candidate."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
        candidate.delete()
        return JsonResponse({'success': True})
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)


@api_login_required
def update_candidate(request, reg_number):
    """Update a candidate."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)
    
    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    subjects_json = request.POST.get('subjects', '')
    
    if name:
        candidate.name = name
    if email:
        candidate.email = email
    if phone:
        candidate.phone = phone
    if subjects_json:
        try:
            candidate.subjects = json.loads(subjects_json)
        except:
            pass
    
    photo = request.FILES.get('photo')
    if photo:
        candidate.photo = photo
    
    candidate.save()
    
    return JsonResponse({'success': True, 'candidate': {
        'id': candidate.id,
        'name': candidate.name,
        'reg_number': candidate.reg_number,
        'photo': candidate.photo_url,
        'subjects': candidate.subjects,
    }})


@api_login_required
def toggle_pause_messaging(request, reg_number):
    """Toggle messaging pause for a candidate."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
        candidate.messaging_paused = not candidate.messaging_paused
        candidate.save()
        
        # Notify candidate
        create_notification(
            'candidate', candidate.reg_number,
            f'Your messaging has been {"paused" if candidate.messaging_paused else "unpaused"} by the admin.',
            'system'
        )
        
        return JsonResponse({
            'success': True,
            'messaging_paused': candidate.messaging_paused
        })
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)


@api_login_required
def toggle_can_message(request, reg_number):
    """Toggle whether a candidate can message."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
        candidate.can_message = not candidate.can_message
        candidate.save()
        
        status = 'enabled' if candidate.can_message else 'disabled'
        create_notification(
            'candidate', candidate.reg_number,
            f'Your messaging privilege has been {status} by the admin.',
            'system'
        )
        
        return JsonResponse({
            'success': True,
            'can_message': candidate.can_message
        })
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)


# ============== MESSAGES ==============

def get_messages(request, user_type, user_id):
    """Get messages for a user."""
    # Check auth
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    other_user = request.GET.get('other', '')
    
    if user_type == 'admin':
        # Admin getting messages with a candidate
        messages = Message.objects.filter(
            (Q(sender_type='admin') & Q(receiver_id=other_user)) |
            (Q(sender_type='candidate', sender_id=other_user) & Q(receiver_type='admin'))
        ).order_by('created_at')
    else:
        # Candidate getting messages
        candidate = Candidate.objects.get(id=candidate_id)
        messages = Message.objects.filter(
            (Q(sender_type='candidate', sender_id=candidate.reg_number) & Q(receiver_id=other_user)) |
            (Q(sender_type='admin', receiver_type='candidate', receiver_id=candidate.reg_number)) |
            (Q(sender_type='candidate', receiver_id=candidate.reg_number))
        ).order_by('created_at')
    
    data = []
    for msg in messages:
        data.append({
            'id': msg.id,
            'sender_type': msg.sender_type,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'receiver_id': msg.receiver_id,
            'receiver_name': msg.receiver_name,
            'content': msg.content,
            'is_read': msg.is_read,
            'created_at': msg.created_at.isoformat(),
        })
    
    return JsonResponse({'messages': data})


def send_message(request):
    """Send a message."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    
    if admin_session:
        sender_type = 'admin'
        sender_id = 'admin'
        sender_name = 'Administrator'
    else:
        sender_type = 'candidate'
        candidate = Candidate.objects.get(id=candidate_id)
        
        # Check if candidate can message
        if not candidate.can_message:
            return JsonResponse({'error': 'You need to unlock messaging first'}, status=403)
        if candidate.messaging_paused:
            return JsonResponse({'error': 'Your messaging has been paused by the admin'}, status=403)
        
        sender_id = candidate.reg_number
        sender_name = candidate.name
    
    receiver_type = data.get('receiver_type', '')
    receiver_id = data.get('receiver_id', '')
    receiver_name = data.get('receiver_name', '')
    content = data.get('content', '').strip()
    
    if not content:
        return JsonResponse({'error': 'Content is required'}, status=400)
    
    message = Message.objects.create(
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        receiver_type=receiver_type,
        receiver_id=receiver_id,
        receiver_name=receiver_name,
        content=content,
    )
    
    # Create notification for receiver
    create_notification(
        receiver_type, receiver_id,
        f'New message from {sender_name}',
        'message',
        f'/chat/{sender_id}'
    )
    
    return JsonResponse({
        'success': True,
        'message': {
            'id': message.id,
            'sender_type': message.sender_type,
            'sender_name': message.sender_name,
            'content': message.content,
            'created_at': message.created_at.isoformat(),
        }
    })


def mark_read(request, message_id):
    """Mark a message as read."""
    try:
        message = Message.objects.get(id=message_id)
        message.is_read = True
        message.save()
        return JsonResponse({'success': True})
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Message not found'}, status=404)


def unread_count(request):
    """Get unread message count."""
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if admin_session:
        count = Message.objects.filter(receiver_type='admin', is_read=False).count()
        return JsonResponse({'count': count})
    elif candidate_id:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            count = Message.objects.filter(receiver_id=candidate.reg_number, is_read=False).count()
            return JsonResponse({'count': count})
        except Candidate.DoesNotExist:
            return JsonResponse({'count': 0})
    
    return JsonResponse({'error': 'Unauthorized'}, status=401)


# ============== GROUPS ==============

def groups_list(request):
    """Get all chat groups."""
    ensure_default_groups()
    
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    groups = ChatGroup.objects.filter(is_active=True)
    
    # Filter groups for candidates
    if candidate_id:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            filtered_groups = []
            for group in groups:
                if group.group_type == 'general':
                    filtered_groups.append(group)
                elif group.subject_name and group.subject_name in candidate.subjects:
                    filtered_groups.append(group)
            groups = filtered_groups
        except Candidate.DoesNotExist:
            pass
    
    data = []
    for group in groups:
        data.append({
            'id': group.id,
            'name': group.name,
            'display_name': group.display_name,
            'group_type': group.group_type,
            'subject_name': group.subject_name,
            'description': group.description,
            'icon': group.icon,
            'admin_only_post': group.admin_only_post,
            'member_count': group.member_count,
            'created_at': group.created_at.isoformat(),
        })
    
    return JsonResponse({'groups': data})


def group_messages(request, group_id):
    """Get messages for a group."""
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        group = ChatGroup.objects.get(id=group_id)
    except ChatGroup.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    
    messages = GroupMessage.objects.filter(group=group).order_by('created_at')[:500]
    
    data = []
    for msg in messages:
        data.append({
            'id': msg.id,
            'sender_type': msg.sender_type,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'sender_photo': msg.sender_photo,
            'content': msg.content,
            'message_type': msg.message_type,
            'voice_message': msg.voice_message.id if msg.voice_message else None,
            'created_at': msg.created_at.isoformat(),
        })
    
    return JsonResponse({
        'group': {
            'id': group.id,
            'name': group.name,
            'display_name': group.display_name,
            'admin_only_post': group.admin_only_post,
        },
        'messages': data
    })


def send_group_message(request):
    """Send a message to a group. Accessible by both admin and authenticated candidates."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')

    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized. Please log in.'}, status=401)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    group_id = data.get('group_id')
    content = data.get('content', '').strip()
    
    if not group_id or not content:
        return JsonResponse({'error': 'Group ID and content are required'}, status=400)
    
    try:
        group = ChatGroup.objects.get(id=group_id)
    except ChatGroup.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)
    
    # Check if admin-only posting is enabled
    if group.admin_only_post and not admin_session:
        return JsonResponse({'error': 'Only admin can post in this group'}, status=403)
    
    if admin_session:
        sender_type = 'admin'
        sender_id = 'admin'
        sender_name = 'Administrator'
        sender_photo = None
    else:
        candidate = Candidate.objects.get(id=candidate_id)
        
        if candidate.messaging_paused:
            return JsonResponse({'error': 'Your messaging has been paused'}, status=403)
        
        sender_type = 'candidate'
        sender_id = candidate.reg_number
        sender_name = candidate.name
        sender_photo = request.build_absolute_uri(candidate.photo_url) if candidate.photo else None
    
    message = GroupMessage.objects.create(
        group=group,
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        sender_photo=sender_photo,
        content=content,
    )
    
    return JsonResponse({
        'success': True,
        'message': {
            'id': message.id,
            'sender_type': message.sender_type,
            'sender_name': message.sender_name,
            'content': message.content,
            'created_at': message.created_at.isoformat(),
        }
    })


@api_login_required
def toggle_admin_only(request, group_id):
    """Toggle admin-only posting for a group."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        group = ChatGroup.objects.get(id=group_id)
        group.admin_only_post = not group.admin_only_post
        group.save()
        
        return JsonResponse({
            'success': True,
            'admin_only_post': group.admin_only_post
        })
    except ChatGroup.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)


# ============== VOICE MESSAGES ==============

@csrf_exempt
def upload_voice(request):
    """Upload a voice message."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    admin_session = request.session.get('admin_logged_in')
    candidate_id = request.session.get('candidate_id')
    
    if not admin_session and not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    audio_file = request.FILES.get('audio')
    duration = int(request.POST.get('duration', 0))
    receiver_type = request.POST.get('receiver_type', '')
    receiver_id = request.POST.get('receiver_id', '')
    group_id = request.POST.get('group_id', '')
    
    if not audio_file:
        return JsonResponse({'error': 'Audio file is required'}, status=400)
    ok, err = validate_upload(audio_file, ALLOWED_AUDIO_TYPES, MAX_AUDIO_SIZE)
    if not ok:
        return JsonResponse({'error': f'Audio upload rejected: {err}'}, status=400)
    
    if admin_session:
        sender_type = 'admin'
        sender_id = 'admin'
        sender_name = 'Administrator'
    else:
        candidate = Candidate.objects.get(id=candidate_id)
        sender_type = 'candidate'
        sender_id = candidate.reg_number
        sender_name = candidate.name
    
    voice = VoiceMessage.objects.create(
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        receiver_type=receiver_type,
        receiver_id=receiver_id,
        duration_seconds=duration,
    )
    
    voice.audio_file = audio_file
    voice.save()
    
    # If group_id is provided, create a group message with voice
    if group_id:
        try:
            group = ChatGroup.objects.get(id=int(group_id))
            GroupMessage.objects.create(
                group=group,
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=sender_name,
                content='[Voice Message]',
                message_type='voice',
                voice_message=voice,
            )
        except ChatGroup.DoesNotExist:
            pass
    
    return JsonResponse({
        'success': True,
        'voice_id': voice.id,
        'duration': voice.duration_display,
        'audio_url': voice.audio_file.url if voice.audio_file else None,
    })


def get_voice(request, voice_id):
    """Get a voice message."""
    try:
        voice = VoiceMessage.objects.get(id=voice_id)
        return JsonResponse({
            'id': voice.id,
            'sender_name': voice.sender_name,
            'duration': voice.duration_display,
            'audio_url': voice.audio_file.url if voice.audio_file else None,
            'created_at': voice.created_at.isoformat(),
        })
    except VoiceMessage.DoesNotExist:
        return JsonResponse({'error': 'Voice message not found'}, status=404)


# ============== UNLOCK SYSTEM ==============

def verify_unlock_password(request):
    """Verify the unlock password."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    candidate_id = request.session.get('candidate_id')
    if not candidate_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    password = data.get('password', '').strip()
    
    if not password:
        return JsonResponse({'error': 'Password is required'}, status=400)
    
    correct_password = get_unlock_password_value()
    
    if password == correct_password:
        try:
            candidate = Candidate.objects.get(id=candidate_id)
            candidate.can_message = True
            candidate.save()
            
            UnlockRecord.objects.create(
                candidate=candidate,
                password_used=password,
                ip_address=get_client_ip(request)
            )
            
            create_notification(
                'admin', 'admin',
                f'{candidate.name} ({candidate.reg_number}) has unlocked premium messaging.',
                'unlock'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Messaging unlocked!'
            })
        except Candidate.DoesNotExist:
            return JsonResponse({'error': 'Candidate not found'}, status=404)
    
    return JsonResponse({'error': 'Incorrect password'}, status=400)


@api_login_required
def get_unlock_password(request):
    """Get the current unlock password (admin only - masked)."""
    password = get_unlock_password_value()
    return JsonResponse({
        'password_masked': '*' * len(password),
        'length': len(password),
    })


@api_login_required
def change_unlock_password(request):
    """Change the unlock password."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    new_password = data.get('new_password', '').strip()
    
    if not new_password or len(new_password) < 2:
        return JsonResponse({'error': 'Password must be at least 2 characters'}, status=400)
    
    AppSettings.set_value('unlock_password', new_password, 'Password to unlock messaging feature')
    
    return JsonResponse({
        'success': True,
        'message': 'Unlock password updated successfully'
    })


@api_login_required
def unlock_records(request):
    """Get all unlock records (admin only)."""
    records = UnlockRecord.objects.all().order_by('-unlocked_at')
    data = []
    for record in records:
        data.append({
            'id': record.id,
            'candidate_name': record.candidate.name,
            'candidate_reg': record.candidate.reg_number,
            'unlocked_at': record.unlocked_at.isoformat(),
            'ip_address': record.ip_address,
        })
    return JsonResponse({'records': data})


# ============== NOTIFICATIONS ==============

def get_notifications(request, user_type, user_id):
    """Get notifications for a user."""
    notifications = Notification.objects.filter(
        user_type=user_type,
        user_identifier=user_id
    ).order_by('-created_at')[:20]
    
    data = []
    for n in notifications:
        data.append({
            'id': n.id,
            'message': n.message,
            'type': n.notification_type,
            'is_read': n.is_read,
            'link': n.link,
            'created_at': n.created_at.isoformat(),
        })
    
    unread_count = Notification.objects.filter(
        user_type=user_type,
        user_identifier=user_id,
        is_read=False
    ).count()
    
    return JsonResponse({
        'notifications': data,
        'unread_count': unread_count
    })


def mark_notification_read(request, notification_id):
    """Mark a notification as read."""
    try:
        notification = Notification.objects.get(id=notification_id)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'error': 'Notification not found'}, status=404)


# ============== DASHBOARD STATS ==============

@api_login_required
def dashboard_stats(request):
    """Get dashboard statistics."""
    stats = {
        'total_candidates': Candidate.objects.count(),
        'active_candidates': Candidate.objects.filter(online=True).count(),
        'total_private_messages': Message.objects.count(),
        'total_group_messages': GroupMessage.objects.count(),
        'suspended_count': Candidate.objects.filter(is_active=False).count(),
        'messaging_paused_count': Candidate.objects.filter(messaging_paused=True).count(),
        'unlocked_count': Candidate.objects.filter(can_message=True).count(),
        'total_voice_messages': VoiceMessage.objects.count(),
        'total_unlock_records': UnlockRecord.objects.count(),
        'recent_candidates': [],
        'recent_unlocks': [],
    }
    
    # Recent candidates
    for c in Candidate.objects.order_by('-created_at')[:5]:
        stats['recent_candidates'].append({
            'name': c.name,
            'reg_number': c.reg_number,
            'created_at': c.created_at.isoformat(),
        })
    
    # Recent unlocks
    for u in UnlockRecord.objects.order_by('-unlocked_at')[:5]:
        stats['recent_unlocks'].append({
            'candidate_name': u.candidate.name,
            'candidate_reg': u.candidate.reg_number,
            'unlocked_at': u.unlocked_at.isoformat(),
        })
    
    return JsonResponse(stats)


# ============== PDF GENERATION ==============

def generate_candidate_pdf_buffer(candidate):
    """Generate a PDF and return as BytesIO buffer — no disk writes needed."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'UTMETitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#667eea'),
        alignment=TA_CENTER,
        spaceAfter=30,
    )
    
    heading_style = ParagraphStyle(
        'UTMEHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#764ba2'),
        spaceAfter=12,
        spaceBefore=12,
    )
    
    info_style = ParagraphStyle(
        'UTMEInfo',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=8,
    )
    
    # Header
    elements.append(Paragraph('UTME SQUAD', title_style))
    elements.append(Spacer(1, 10))
    
    # Subtitle
    subtitle_style = ParagraphStyle(
        'UTMESubtitle',
        parent=styles['Normal'],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#666666'),
        spaceAfter=30,
    )
    elements.append(Paragraph('Candidate Registration Details', subtitle_style))
    elements.append(Spacer(1, 20))
    
    # Photo
    if candidate.photo:
        try:
            img = Image(candidate.photo.path, width=120, height=120)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 20))
        except:
            pass
    
    # Candidate Info Table
    data = [
        ['Full Name:', candidate.name],
        ['Registration Number:', candidate.reg_number],
        ['Email:', candidate.email or 'N/A'],
        ['Phone:', candidate.phone or 'N/A'],
        ['Password:', '[ See registration card ]'],  # password shown at registration time only
        ['Status:', 'Active' if candidate.is_active else 'Suspended'],
        ['Messaging:', 'Unlocked' if candidate.can_message else 'Locked'],
    ]
    
    table = Table(data, colWidths=[150, 250])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 25))
    
    # Subjects
    elements.append(Paragraph('Registered Subjects', heading_style))
    elements.append(Spacer(1, 10))
    
    subject_data = [['Subject', 'Status']]
    for subject in candidate.subjects:
        subject_data.append([subject, 'Registered'])
    
    subject_table = Table(subject_data, colWidths=[200, 200])
    subject_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elements.append(subject_table)
    elements.append(Spacer(1, 30))
    
    # Footer
    footer_style = ParagraphStyle(
        'UTMEFooter',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#999999'),
    )
    elements.append(Paragraph(f'Generated on {datetime.now().strftime("%B %d, %Y at %I:%M %p")}', footer_style))
    elements.append(Spacer(1, 5))
    elements.append(Paragraph('UTME SQUAD - Secure Educational Platform', footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_candidate_pdf_file(candidate):
    """Legacy wrapper — kept for backwards compatibility."""
    buffer = generate_candidate_pdf_buffer(candidate)
    filename = f'UTME_SQUAD_{candidate.reg_number}.pdf'
    try:
        filepath = os.path.join(settings.MEDIA_ROOT, 'candidate_files', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(buffer.getvalue())
    except Exception:
        pass  # Ephemeral filesystem — skip saving
    return filename


@api_login_required
def generate_candidate_pdf(request, reg_number):
    """Generate and stream PDF directly - works on ephemeral file systems like Render."""
    try:
        candidate = Candidate.objects.get(reg_number=reg_number)
    except Candidate.DoesNotExist:
        return JsonResponse({'error': 'Candidate not found'}, status=404)

    try:
        pdf_buffer = generate_candidate_pdf_buffer(candidate)
        filename = f'UTME_SQUAD_{candidate.reg_number}.pdf'
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'PDF generation failed: {str(e)}'}, status=500)


# ============== SETTINGS ==============

@api_login_required
def get_settings(request):
    """Get application settings."""
    settings_list = AppSettings.objects.all()
    data = {}
    for s in settings_list:
        if s.key == 'unlock_password':
            data[s.key] = '*' * len(s.value)
        elif s.key == 'admin_password':
            data[s.key] = '*' * len(s.value)
        else:
            data[s.key] = s.value
    return JsonResponse(data)


@api_login_required
def update_settings(request):
    """Update application settings."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    for key, value in data.items():
        AppSettings.set_value(key, value)
    
    return JsonResponse({'success': True})


@api_login_required
def change_admin_password(request):
    """Change admin password."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    
    if not current_password or not new_password:
        return JsonResponse({'error': 'Both passwords are required'}, status=400)
    
    admin_password = get_admin_password_value()
    
    if not verify_password(current_password, admin_password):
        return JsonResponse({'error': 'Current password is incorrect'}, status=400)
    
    AppSettings.set_value('admin_password', hash_password(new_password), 'Admin login password')
    
    return JsonResponse({'success': True, 'message': 'Admin password changed successfully'})
