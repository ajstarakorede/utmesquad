from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('auth/admin-login/', views.api_admin_login, name='api_admin_login'),
    path('auth/admin-logout/', views.api_admin_logout, name='api_admin_logout'),
    path('auth/candidate-login/', views.api_candidate_login, name='api_candidate_login'),
    path('auth/candidate-logout/', views.api_candidate_logout, name='api_candidate_logout'),
    
    # Candidates
    path('candidates/', views.candidates_list, name='api_candidates_list'),
    path('candidates/register/', views.register_candidate, name='api_register_candidate'),
    path('candidates/<str:reg_number>/delete/', views.delete_candidate, name='api_delete_candidate'),
    path('candidates/<str:reg_number>/update/', views.update_candidate, name='api_update_candidate'),
    path('candidates/<str:reg_number>/toggle-pause/', views.toggle_pause_messaging, name='api_toggle_pause'),
    path('candidates/<str:reg_number>/toggle-message/', views.toggle_can_message, name='api_toggle_message'),
    path('candidates/<str:reg_number>/generate-pdf/', views.generate_candidate_pdf, name='api_generate_pdf'),
    path('candidates/<str:reg_number>/', views.candidate_detail, name='api_candidate_detail'),
    
    # Messages - specific routes BEFORE parametric routes
    path('messages/send/', views.send_message, name='api_send_message'),
    path('messages/unread-count/', views.unread_count, name='api_unread_count'),
    path('messages/<int:message_id>/read/', views.mark_read, name='api_mark_read'),
    path('messages/<str:user_type>/<str:user_id>/', views.get_messages, name='api_get_messages'),
    
    # Groups
    path('groups/', views.groups_list, name='api_groups_list'),
    path('groups/<int:group_id>/send/', views.send_group_message, name='api_send_group_message'),
    path('groups/send/', views.send_group_message, name='api_send_group_message_flat'),  # body-based route
    path('groups/<int:group_id>/toggle-admin-only/', views.toggle_admin_only, name='api_toggle_admin_only'),
    path('groups/<int:group_id>/messages/', views.group_messages, name='api_group_messages'),
    
    # Voice messages
    path('voice/upload/', views.upload_voice, name='api_upload_voice'),
    path('voice/<int:voice_id>/', views.get_voice, name='api_get_voice'),
    
    # Unlock system
    path('unlock/verify/', views.verify_unlock_password, name='api_verify_unlock'),
    path('unlock/password/change/', views.change_unlock_password, name='api_change_unlock_password'),
    path('unlock/password/', views.get_unlock_password, name='api_get_unlock_password'),
    path('unlock/records/', views.unlock_records, name='api_unlock_records'),
    
    # Notifications
    path('notifications/<str:user_type>/<str:user_id>/', views.get_notifications, name='api_get_notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='api_mark_notification_read'),
    
    # Dashboard stats
    path('dashboard/stats/', views.dashboard_stats, name='api_dashboard_stats'),
    
    # Settings
    path('settings/update/', views.update_settings, name='api_update_settings'),
    path('settings/admin-password/', views.change_admin_password, name='api_change_admin_password'),
    path('settings/', views.get_settings, name='api_get_settings'),
]
