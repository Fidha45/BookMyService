import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse

from .models import Booking

logger = logging.getLogger(__name__)

EVENT_COPY = {
    "booking_request": ("Booking request received", "Your booking request has been sent to the provider."),
    "new_booking_request": ("New booking request", "A customer has requested one of your services."),
    "accepted": ("Booking accepted", "The provider accepted your booking request."),
    "rejected": ("Booking declined", "The provider could not accept your booking request."),
    "in_progress": ("Service in progress", "The provider has started your service."),
    "awaiting_customer_confirmation": ("Please confirm your completed service", "Your provider marked the service as finished. Confirm completion from My Bookings."),
    "completed": ("Service completion confirmed", "Your service is now marked as completed."),
    "cancelled": ("Booking cancelled", "Your booking has been cancelled."),
    "cancelled_by_customer": ("Booking cancelled by customer", "The customer cancelled this booking."),
    "rescheduled": ("Booking rescheduled", "The booking time has changed. Please review the updated schedule."),
}


def queue_booking_email(booking_id, recipient_id, event_key):
    """Send once after commit; mail failures never change the booking transaction."""
    transaction.on_commit(
        lambda: _send_booking_email(booking_id, recipient_id, event_key),
        robust=True,
    )


def _send_booking_email(booking_id, recipient_id, event_key):
    try:
        from accounts.models import User

        booking = Booking.objects.select_related(
            "customer", "service", "service__provider", "service__provider__user"
        ).get(pk=booking_id)
        recipient = User.objects.get(pk=recipient_id)
        if not recipient.email:
            return

        title, intro = EVENT_COPY.get(event_key, ("Booking update", "There is an update to your booking."))
        provider = booking.service.provider
        start_at = timezone.localtime(booking.start_at)
        context = {
            "event_title": title,
            "intro": intro,
            "recipient_name": recipient.first_name or (provider.display_name if recipient == provider.user else "there"),
            "customer_name": booking.customer.get_full_name() or booking.customer.email,
            "service_name": booking.service.name,
            "booking_id": booking.pk,
            "booking_reference": booking.reference,
            "booking_date": start_at.strftime("%A, %d %B %Y"),
            "booking_time": start_at.strftime("%I:%M %p").lstrip("0"),
            "provider_name": provider.display_name,
            "booking_status": booking.get_status_display(),
            "booking_url": f"{settings.SITE_URL.rstrip('/')}{reverse('dashboard')}" if getattr(settings, "SITE_URL", "") else "",
        }
        subject = f"{title} Â· BookMyService"
        text_body = render_to_string("emails/booking_notification.txt", context)
        html_body = render_to_string("emails/booking_notification.html", context)
        email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [recipient.email])
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
    except Exception:
        logger.exception("Unable to send booking email for booking %s (%s).", booking_id, event_key)
