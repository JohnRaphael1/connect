from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    User, Friendship, BlockList, Post, Like, Comment,
    Chat, ChatMember, Message, MessageReaction, TypingStatus, Sticker,
    Notification, SupportTicket,
)


# ============================================================
# USER
# ============================================================
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email', 'full_name', 'username', 'phone',
        'is_active', 'active_status', 'is_deactivated', 'is_staff', 'date_joined',
    )
    list_filter = (
        'is_staff', 'is_superuser', 'is_active', 'is_private',
        'is_deactivated', 'active_status', 'gender',
    )
    search_fields = ('email', 'username', 'phone', 'full_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': (
            'full_name', 'phone', 'dob', 'gender', 'profile_pic', 'banner',
        )}),
        ('Privacy & status', {'fields': (
            'is_private', 'active_status', 'is_deactivated', 'deactivated_at',
        )}),
        ('Permissions', {'fields': (
            'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions',
        )}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'full_name', 'password1', 'password2'),
        }),
    )

    def profile_pic_preview(self, obj):
        if obj.profile_pic and obj.profile_pic.name != 'profiles/default.png':
            return format_html('<img src="{}" style="width:32px;height:32px;border-radius:50%;" />', obj.profile_pic.url)
        return '—'
    profile_pic_preview.short_description = 'Pic'


# ============================================================
# FRIENDSHIP
# ============================================================
@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'friend', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = (
        'user__username', 'user__full_name', 'user__email',
        'friend__username', 'friend__full_name', 'friend__email',
    )
    date_hierarchy = 'created_at'
    autocomplete_fields = ('user', 'friend')


# ============================================================
# BLOCK LIST
# ============================================================
@admin.register(BlockList)
class BlockListAdmin(admin.ModelAdmin):
    list_display = ('id', 'blocker', 'blocked', 'is_permanent')
    list_filter = ('is_permanent',)
    search_fields = (
        'blocker__username', 'blocker__email',
        'blocked__username', 'blocked__email',
    )
    autocomplete_fields = ('blocker', 'blocked')


# ============================================================
# POST
# ============================================================
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'short_text', 'has_image', 'has_video', 'likes_count', 'comments_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'text')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user',)

    def short_text(self, obj):
        if obj.text:
            return obj.text[:60] + ('…' if len(obj.text) > 60 else '')
        return '—'
    short_text.short_description = 'Text'

    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Image'

    def has_video(self, obj):
        return bool(obj.video)
    has_video.boolean = True
    has_video.short_description = 'Video'

    def likes_count(self, obj):
        return obj.likes.count()
    likes_count.short_description = 'Likes'

    def comments_count(self, obj):
        return obj.comments.count()
    comments_count.short_description = 'Comments'


# ============================================================
# LIKE
# ============================================================
@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'post_owner')
    search_fields = ('user__username', 'user__email', 'post__user__username')
    autocomplete_fields = ('user', 'post')

    def post_owner(self, obj):
        return obj.post.user.full_name or obj.post.user.username
    post_owner.short_description = 'Post owner'


# ============================================================
# COMMENT
# ============================================================
@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'post', 'short_text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'text')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('user', 'post')

    def short_text(self, obj):
        return obj.text[:60] + ('…' if len(obj.text) > 60 else '')
    short_text.short_description = 'Comment'


# ============================================================
# CHAT
# ============================================================
class ChatMemberInline(admin.TabularInline):
    model = ChatMember
    extra = 1
    autocomplete_fields = ('user',)
    fields = ('user', 'is_admin', 'is_muted', 'is_pinned', 'is_archived', 'is_favourite', 'is_locked', 'lock_code')


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'display_name', 'chat_type', 'members_count', 'messages_count', 'created_by', 'created_at')
    list_filter = ('chat_type', 'created_at')
    search_fields = ('name', 'created_by__username', 'created_by__email')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    autocomplete_fields = ('created_by',)
    inlines = [ChatMemberInline]

    def display_name(self, obj):
        return obj.name or f"Chat #{obj.id}"
    display_name.short_description = 'Name'

    def members_count(self, obj):
        return obj.members.count()
    members_count.short_description = 'Members'

    def messages_count(self, obj):
        return obj.messages.filter(deleted=False).count()
    messages_count.short_description = 'Messages'


# ============================================================
# CHAT MEMBER
# ============================================================
@admin.register(ChatMember)
class ChatMemberAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat', 'user', 'is_admin', 'is_muted', 'is_pinned', 'is_favourite', 'is_locked', 'joined_at')
    list_filter = ('is_admin', 'is_muted', 'is_pinned', 'is_favourite', 'is_locked')
    search_fields = ('user__username', 'user__email', 'chat__name')
    date_hierarchy = 'joined_at'
    autocomplete_fields = ('chat', 'user')


# ============================================================
# MESSAGE
# ============================================================
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat', 'sender', 'short_text', 'message_type', 'is_read', 'deleted', 'timestamp')
    list_filter = ('message_type', 'is_read', 'deleted', 'timestamp')
    search_fields = ('sender__username', 'sender__email', 'text')
    date_hierarchy = 'timestamp'
    readonly_fields = ('timestamp',)
    autocomplete_fields = ('chat', 'sender', 'receiver')

    def short_text(self, obj):
        if obj.text:
            return obj.text[:60] + ('…' if len(obj.text) > 60 else '')
        return f"[{obj.message_type}]"
    short_text.short_description = 'Text'


# ============================================================
# MESSAGE REACTION
# ============================================================
@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'message', 'user', 'emoji')
    search_fields = ('user__username', 'emoji')
    autocomplete_fields = ('message', 'user')


# ============================================================
# TYPING STATUS
# ============================================================
@admin.register(TypingStatus)
class TypingStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat', 'user', 'updated_at')
    list_filter = ('updated_at',)
    search_fields = ('user__username', 'chat__name')
    autocomplete_fields = ('chat', 'user')


# ============================================================
# STICKER
# ============================================================
@admin.register(Sticker)
class StickerAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'preview', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user',)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:40px;height:40px;object-fit:cover;border-radius:6px;" />', obj.image.url)
        return '—'
    preview.short_description = 'Preview'


# ============================================================
# NOTIFICATION
# ============================================================
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'sender', 'notif_type', 'is_read', 'created_at')
    list_filter = ('notif_type', 'is_read', 'created_at')
    search_fields = ('user__username', 'sender__username', 'user__email', 'sender__email')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('user', 'sender')


# ============================================================
# SUPPORT TICKET
# ============================================================
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'short_message', 'resolved', 'created_at')
    list_filter = ('resolved', 'created_at')
    search_fields = ('user__username', 'user__email', 'subject', 'message')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
    list_editable = ('resolved',)
    autocomplete_fields = ('user',)

    def short_message(self, obj):
        return obj.message[:80] + ('…' if len(obj.message) > 80 else '')
    short_message.short_description = 'Message'


# ============================================================
# ADMIN SITE BRANDING
# ============================================================
admin.site.site_header = "Connect Administration"
admin.site.site_title = "Connect Admin"
admin.site.index_title = "Manage your platform"