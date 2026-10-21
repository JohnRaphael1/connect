from .models import Notification, Message


def notification_counts(request):
    if not request.user.is_authenticated:
        return {}
    return {
        'unread_notifs': Notification.objects.filter(user=request.user, is_read=False).count(),
        'unread_messages': Message.objects.filter(receiver=request.user, is_read=False).count(),
    }