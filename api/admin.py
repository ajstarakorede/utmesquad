from django.contrib import admin
from .models import (
    Candidate, Message, ChatGroup, GroupMessage,
    UnlockRecord, AppSettings, Notification,
    VoiceMessage, SubjectGroup, CandidateFile
)

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('name', 'reg_number', 'email', 'is_active', 'messaging_paused', 'can_message', 'created_at')
    list_filter = ('is_active', 'messaging_paused', 'can_message')
    search_fields = ('name', 'reg_number', 'email', 'phone')
    readonly_fields = ('created_at', 'last_active', 'login_count')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender_name', 'receiver_name', 'content_preview', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('sender_name', 'receiver_name', 'content')

@admin.register(ChatGroup)
class ChatGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'group_type', 'subject_name', 'created_at')
    list_filter = ('group_type',)

@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ('sender_name', 'group', 'content_preview', 'created_at')
    list_filter = ('group', 'created_at')

@admin.register(UnlockRecord)
class UnlockRecordAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'unlocked_at', 'ip_address')
    list_filter = ('unlocked_at',)

@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ('key', 'value_preview', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user_type', 'user_identifier', 'message_preview', 'is_read', 'created_at')
    list_filter = ('is_read', 'user_type', 'created_at')

@admin.register(VoiceMessage)
class VoiceMessageAdmin(admin.ModelAdmin):
    list_display = ('sender_name', 'sender_type', 'duration_display', 'created_at')
    list_filter = ('created_at',)

@admin.register(SubjectGroup)
class SubjectGroupAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'display_name', 'created_at')

@admin.register(CandidateFile)
class CandidateFileAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'file_type', 'created_at')
    list_filter = ('file_type',)
