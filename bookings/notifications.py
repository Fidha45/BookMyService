from django.urls import reverse
from .models import Notification


def notify_booking(booking, event, message, recipient, email_event=None):
    notification, created = Notification.objects.get_or_create(
        event_key=f"booking:{booking.pk}:{event}:{recipient.pk}",
        defaults={"recipient": recipient, "booking": booking, "message": message,
                  "url": reverse("dashboard")},
    )
    if created and email_event:
        from .email_notifications import queue_booking_email
        queue_booking_email(booking.pk, recipient.pk, email_event)
    return notification
