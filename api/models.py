from django.db import models
import json


class Candidate(models.Model):
    """Represents a registered UTME candidate/student."""
    
    SUBJECT_CHOICES = [
        ('English', 'English'),
        ('Mathematics', 'Mathematics'),
        ('Physics', 'Physics'),
        ('Chemistry', 'Chemistry'),
        ('Biology', 'Biology'),
        ('Government', 'Government'),
        ('Literature', 'Literature'),
        ('CRS', 'CRS'),
        ('IRS', 'IRS'),
        ('Economics', 'Economics'),
        ('Commerce', 'Commerce'),
    ]
    
    reg_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    password = models.CharField(max_length=128, default='candidate123')
    photo = models.ImageField(upload_to='candidate_photos/', blank=True, null=True)
    subjects_json = models.TextField(default='["English"]')
    
    # Status fields
    is_active = models.BooleanField(default=True)
    online = models.BooleanField(default=False)
    messaging_paused = models.BooleanField(default=False)
    can_message = models.BooleanField(default=False)  # Premium feature - unlocked by password
    can_message_override = models.BooleanField(default=True)  # Admin override for messaging
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)
    login_count = models.IntegerField(default=0)
    
    # Exam stats
    exams_taken = models.IntegerField(default=0)
    avg_score = models.FloatField(default=0.0)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'candidates'
    
    def __str__(self):
        return f"{self.name} ({self.reg_number})"
    
    @property
    def subjects(self):
        try:
            return json.loads(self.subjects_json)
        except:
            return ['English']
    
    @subjects.setter
    def subjects(self, value):
        self.subjects_json = json.dumps(value)
    
    @property
    def photo_url(self):
        if self.photo:
            return self.photo.url
        return '/static/images/default-avatar.svg'
    
    @property
    def status_display(self):
        if not self.is_active:
            return 'suspended'
        if self.online:
            return 'online'
        return 'offline'


class Message(models.Model):
    """Private messages between users (admin-candidate or candidate-candidate when unlocked)."""
    
    sender_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
    ])
    sender_id = models.CharField(max_length=20)
    sender_name = models.CharField(max_length=200)
    
    receiver_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
    ])
    receiver_id = models.CharField(max_length=20)
    receiver_name = models.CharField(max_length=200)
    
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    
    # For reply functionality
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'messages'
    
    def __str__(self):
        return f"{self.sender_name} -> {self.receiver_name}: {self.content[:50]}"
    
    @property
    def content_preview(self):
        return self.content[:50] + '...' if len(self.content) > 50 else self.content


class VoiceMessage(models.Model):
    """Voice message recordings."""
    
    sender_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
    ])
    sender_id = models.CharField(max_length=20)
    sender_name = models.CharField(max_length=200)
    
    receiver_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
        ('group', 'Group'),
    ])
    receiver_id = models.CharField(max_length=20)
    
    # Can be attached to a specific group or private chat
    group = models.ForeignKey('ChatGroup', on_delete=models.CASCADE, null=True, blank=True)
    
    audio_file = models.FileField(upload_to='voice_messages/')
    duration_seconds = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'voice_messages'
    
    def __str__(self):
        return f"Voice from {self.sender_name} ({self.duration_seconds}s)"
    
    @property
    def duration_display(self):
        mins = self.duration_seconds // 60
        secs = self.duration_seconds % 60
        return f"{mins}:{secs:02d}"


class ChatGroup(models.Model):
    """Chat groups including UTME SQUAD general group and subject groups."""
    
    GROUP_TYPES = [
        ('general', 'General'),
        ('subject', 'Subject'),
    ]
    
    name = models.CharField(max_length=200)
    display_name = models.CharField(max_length=200)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPES, default='general')
    subject_name = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fa-users')
    
    # Admin controls
    is_active = models.BooleanField(default=True)
    admin_only_post = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['group_type', 'name']
        db_table = 'chat_groups'
    
    def __str__(self):
        return self.display_name
    
    @property
    def member_count(self):
        if self.group_type == 'general':
            return Candidate.objects.filter(is_active=True).count()
        elif self.subject_name:
            # Count candidates who have this subject
            count = 0
            for c in Candidate.objects.filter(is_active=True):
                if self.subject_name in c.subjects:
                    count += 1
            return count
        return 0


class GroupMessage(models.Model):
    """Messages sent in chat groups."""
    
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name='messages')
    
    sender_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
    ])
    sender_id = models.CharField(max_length=20)
    sender_name = models.CharField(max_length=200)
    sender_photo = models.URLField(blank=True, null=True)
    
    content = models.TextField()
    message_type = models.CharField(max_length=20, default='text', choices=[
        ('text', 'Text'),
        ('voice', 'Voice'),
        ('file', 'File'),
        ('announcement', 'Announcement'),
    ])
    
    # For voice messages
    voice_message = models.ForeignKey(VoiceMessage, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        db_table = 'group_messages'
    
    def __str__(self):
        return f"{self.sender_name} in {self.group.name}: {self.content[:50]}"
    
    @property
    def content_preview(self):
        return self.content[:50] + '...' if len(self.content) > 50 else self.content


class SubjectGroup(models.Model):
    """Tracks which subject groups exist and their members."""
    
    subject_name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    chat_group = models.OneToOneField(ChatGroup, on_delete=models.CASCADE, related_name='subject_group')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['subject_name']
        db_table = 'subject_groups'
    
    def __str__(self):
        return self.display_name
    
    @property
    def member_count(self):
        count = 0
        for c in Candidate.objects.filter(is_active=True):
            if self.subject_name in c.subjects:
                count += 1
        return count


class UnlockRecord(models.Model):
    """Tracks which candidates have unlocked the premium messaging feature."""
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='unlock_records')
    password_used = models.CharField(max_length=100)  # The password they entered
    unlocked_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    class Meta:
        ordering = ['-unlocked_at']
        db_table = 'unlock_records'
    
    def __str__(self):
        return f"{self.candidate.name} unlocked at {self.unlocked_at}"


class AppSettings(models.Model):
    """Application settings including unlock password."""
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'app_settings'
        verbose_name_plural = 'App Settings'
    
    def __str__(self):
        return self.key
    
    @property
    def value_preview(self):
        if self.key == 'unlock_password':
            return '*' * len(self.value) if self.value else 'Not set'
        return self.value[:50]
    
    @classmethod
    def get_value(cls, key, default=None):
        try:
            setting = cls.objects.get(key=key)
            return setting.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_value(cls, key, value, description=''):
        setting, created = cls.objects.get_or_create(key=key)
        setting.value = value
        if description:
            setting.description = description
        setting.save()
        return setting


class Notification(models.Model):
    """In-app notifications for users."""
    
    user_type = models.CharField(max_length=20, choices=[
        ('admin', 'Admin'),
        ('candidate', 'Candidate'),
    ])
    user_identifier = models.CharField(max_length=20)  # 'admin' or reg_number
    
    message = models.TextField()
    notification_type = models.CharField(max_length=20, default='message', choices=[
        ('message', 'Message'),
        ('announcement', 'Announcement'),
        ('unlock', 'Unlock'),
        ('system', 'System'),
    ])
    
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'notifications'
    
    def __str__(self):
        return f"{self.user_type}:{self.user_identifier} - {self.message[:50]}"
    
    @property
    def message_preview(self):
        return self.message[:50] + '...' if len(self.message) > 50 else self.message


class CandidateFile(models.Model):
    """Files generated for candidates (e.g., PDF with registration details)."""
    
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='candidate_files/')
    file_type = models.CharField(max_length=20, choices=[
        ('pdf', 'PDF'),
        ('image', 'Image'),
        ('other', 'Other'),
    ])
    description = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'candidate_files'
    
    def __str__(self):
        return f"{self.file_type} for {self.candidate.name}"
