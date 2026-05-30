"""
URL configuration for utme_squad project.
"""
from django.contrib import admin as django_admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api import views as api_views

urlpatterns = [
    # Django admin
    path('django-admin/', django_admin.site.urls),

    # Homepage — redirect to admin login cleanly (no loop)
    path('', lambda request: redirect('/admin/', permanent=False), name='home'),

    # Admin URLs
    path('admin/', api_views.admin_login, name='admin_login'),
    path('admin/dashboard/', api_views.admin_dashboard, name='admin_dashboard'),
    path('admin/logout/', api_views.admin_logout, name='admin_logout'),

    # Candidate URLs
    path('candidate/', lambda request: redirect('/candidate/login/', permanent=False)),
    path('candidate/login/', api_views.candidate_login, name='candidate_login'),
    path('candidate/dashboard/', api_views.candidate_dashboard, name='candidate_dashboard'),
    path('candidate/logout/', api_views.candidate_logout, name='candidate_logout'),
    path('candidate/unlock-messaging/', api_views.unlock_messaging, name='unlock_messaging'),

    # API endpoints
    path('api/', include('api.urls')),

    # Chat WebSocket and HTTP endpoints
    path('chat/', include('chat.urls')),
]

# Static files are served by WhiteNoise middleware in all environments.
# Media files (uploads) must be served by nginx in production.
# For development convenience only:
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
