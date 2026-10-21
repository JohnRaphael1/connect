from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import date

class User(AbstractUser):
    # We override username to use email, but allow phone login
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    email = models.EmailField(max_length=150, unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    full_name = models.CharField(max_length=100)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], blank=True)
    profile_pic = models.ImageField(upload_to='profiles/', default='profiles/default.png', blank=True)
    banner = models.ImageField(upload_to='banners/', default='banners/default.png', blank=True)
    is_private = models.BooleanField(default=False)
    is_deactivated = models.BooleanField(default=False)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    active_status = models.BooleanField(default=True) # Show if online
    
    # Track blocks (Blocked relation handled in a separate model)
    
    def age(self):
        if self.dob:
            return date.today().year - self.dob.year
        return 0

class Friendship(models.Model):
    user = models.ForeignKey(User, related_name='friendships', on_delete=models.CASCADE)
    friend = models.ForeignKey(User, related_name='friend_of', on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('accepted', 'Accepted')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'friend')

class BlockList(models.Model):
    blocker = models.ForeignKey(User, related_name='blocked_users', on_delete=models.CASCADE)
    blocked = models.ForeignKey(User, related_name='blocked_by', on_delete=models.CASCADE)
    # If temporary, you can add a blocked_until DateTimeField here
    is_permanent = models.BooleanField(default=True) 

class Post(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='posts/images/', blank=True, null=True)
    video = models.FileField(upload_to='posts/videos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='likes', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'post')

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)





class Chat(models.Model):
    """A chat thread: either 1-on-1 or group."""
    CHAT_TYPE = [('direct', 'Direct'), ('group', 'Group')]

    chat_type = models.CharField(max_length=10, choices=CHAT_TYPE, default='direct')
    name = models.CharField(max_length=100, blank=True, null=True)     # group name
    avatar = models.ImageField(upload_to='chat_avatars/', blank=True, null=True)  # group avatar
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_chats')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or f"Chat {self.id}"


class ChatMember(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_memberships')
    is_admin = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    is_favourite = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)       # requires code to open
    lock_code = models.CharField(max_length=10, blank=True, null=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('chat', 'user')


class Message(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Text'), ('image', 'Image'), ('video', 'Video'),
        ('document', 'Document'), ('voice', 'Voice'), ('sticker', 'Sticker'),
    ]

    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='received_messages')  # legacy 1-1 compat
    text = models.TextField(blank=True, null=True)
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    attachment = models.FileField(upload_to='messages/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    edited = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']


class MessageReaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=10)

    class Meta:
        unique_together = ('message', 'user')


class TypingStatus(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='typing_statuses')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('chat', 'user')


class Sticker(models.Model):
    """User-defined sticker pack."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stickers')
    image = models.ImageField(upload_to='stickers/')
    name = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user = models.ForeignKey(User, related_name='notifications', on_delete=models.CASCADE) # Who receives it
    sender = models.ForeignKey(User, on_delete=models.CASCADE) # Who triggered it
    notif_type = models.CharField(max_length=20) # 'friend_req', 'like', 'comment', 'message'
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)





class SupportTicket(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.subject} — {self.user.username}"