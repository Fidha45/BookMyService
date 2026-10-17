def notification_count(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    from bookings.models import Notification
    return {"unread_notification_count": Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()}
