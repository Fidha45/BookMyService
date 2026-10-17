from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import F
from django.utils import timezone
from .models import Booking

TRANSITIONS = {
    Booking.Status.PENDING: {Booking.Status.CONFIRMED, Booking.Status.REJECTED, Booking.Status.CANCELLED},
    Booking.Status.CONFIRMED: {Booking.Status.IN_PROGRESS, Booking.Status.CANCELLED},
    Booking.Status.IN_PROGRESS: {Booking.Status.COMPLETED},
}

def _lock_provider_schedule(provider_id):
    """Serialize all slot-affecting writes for one provider.

    PostgreSQL and MySQL use a row lock. SQLite ignores select_for_update(),
    so an atomic version increment acquires its database write lock before any
    availability reads. The transaction then rechecks the slot after waiting.
    """
    from accounts.models import ProviderProfile
    if connection.vendor == "sqlite":
        try:
            locked = ProviderProfile.objects.filter(pk=provider_id).update(
                booking_lock_version=F("booking_lock_version") + 1
            )
        except OperationalError as exc:
            raise ValidationError("The schedule is busy right now. Please try again.") from exc
        if not locked:
            raise ValidationError("This provider is no longer available.")
        return
    try:
        ProviderProfile.objects.select_for_update().get(pk=provider_id)
    except ProviderProfile.DoesNotExist as exc:
        raise ValidationError("This provider is no longer available.") from exc

def available_slots(service, day, step_minutes=30):
    """Return currently open start times for a local calendar date."""
    profile = service.provider
    if not service.is_active or not profile.user.is_active: return []
    hours = profile.availability.filter(weekday=day.weekday()).first()
    if not hours: return []
    tz = timezone.get_current_timezone()
    opening = timezone.make_aware(datetime.combine(day, hours.start_time), tz)
    closing = timezone.make_aware(datetime.combine(day, hours.end_time), tz)
    duration = timedelta(minutes=service.duration_minutes)
    occupied = list(Booking.objects.filter(service__provider=profile, status__in=Booking.OCCUPYING,
                                      start_at__lt=closing, end_at__gt=opening).values_list("start_at", "end_at"))
    from accounts.models import AvailabilityBlock
    blocks = list(AvailabilityBlock.objects.filter(provider=profile, start_at__lt=closing, end_at__gt=opening).values_list("start_at", "end_at"))
    slots, start = [], opening
    while start + duration <= closing:
        end = start + duration
        is_booked = any(busy_start < end and busy_end > start for busy_start, busy_end in occupied)
        is_blocked = any(block_start < end and block_end > start for block_start, block_end in blocks)
        if start > timezone.now() and not is_booked and not is_blocked:
            slots.append(start)
        start += timedelta(minutes=step_minutes)
    return slots

def _schedule_and_overlap(service, start, end, exclude_id=None):
    if not isinstance(start, datetime) or not isinstance(end, datetime) or timezone.is_naive(start) or timezone.is_naive(end):
        raise ValidationError("Choose a valid date and time.")
    if end <= start:
        raise ValidationError("Choose a valid service duration.")
    if start <= timezone.now(): raise ValidationError("Choose a future date and time.")
    profile = service.provider
    if not profile.user.is_active or not service.is_active: raise ValidationError("This provider or service is unavailable.")
    hours = profile.availability.filter(weekday=start.weekday()).first()
    if not hours or start.time() < hours.start_time or end.time() > hours.end_time or start.date() != end.date():
        raise ValidationError("The appointment must fit within the provider's working hours.")
    from accounts.models import AvailabilityBlock
    if AvailabilityBlock.objects.filter(provider=profile, start_at__lt=end, end_at__gt=start).exists():
        raise ValidationError("That period is blocked by the provider. Please choose another time.")
    conflicts = Booking.objects.filter(service__provider=profile, status__in=Booking.OCCUPYING, start_at__lt=end, end_at__gt=start)
    if exclude_id: conflicts = conflicts.exclude(pk=exclude_id)
    if conflicts.exists(): raise ValidationError("Sorry, this time slot has just been booked. Please select another available time.")

def create_booking(customer, service, start, request_key=None):
    if request_key:
        existing = Booking.objects.filter(customer=customer, request_key=request_key).first()
        if existing: return existing
    try:
        with transaction.atomic():
            # Every PostgreSQL booking write locks this existing provider row. That lock
            # serializes the overlap check and insert, even when no matching booking exists.
            _lock_provider_schedule(service.provider_id)
            from services.models import Service
            service = Service.objects.select_for_update().select_related("provider__user").get(pk=service.pk)
            duration = service.duration_minutes
            end = start + timedelta(minutes=duration)
            _schedule_and_overlap(service, start, end)
            booking = Booking.objects.create(customer=customer, service=service, provider_lock_id=service.provider_id, start_at=start, end_at=end,
                price_at_booking=service.price, duration_at_booking=duration, request_key=request_key)
            from .notifications import notify_booking
            notify_booking(booking, "requested", f"Booking request sent for {service.name}.", booking.service.provider.user, "new_booking_request")
            notify_booking(booking, "requested-customer", f"Your request for {service.name} was submitted.", customer, "booking_request")
            return booking
    except IntegrityError as exc:
        if request_key:
            existing = Booking.objects.filter(customer=customer, request_key=request_key).first()
            if existing: return existing
        raise ValidationError("Sorry, this time slot has just been booked. Please select another available time.") from exc

def reschedule_booking(booking, start):
    try:
        with transaction.atomic():
            # Keep the provider-first lock order shared with create_booking() and
            # transition() to avoid provider/booking lock inversion.
            _lock_provider_schedule(booking.provider_lock_id)
            booking = Booking.objects.select_for_update().select_related("service").get(pk=booking.pk)
            if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
                raise ValidationError("This booking can no longer be rescheduled.")
            if booking.start_at <= timezone.now():
                raise ValidationError("Only upcoming bookings can be rescheduled.")
            if booking.start_at == start:
                return booking
            end = start + timedelta(minutes=booking.duration_at_booking)
            from services.models import Service
            service = Service.objects.select_for_update().select_related("provider__user").get(pk=booking.service_id)
            _schedule_and_overlap(service, start, end, exclude_id=booking.pk)
            booking.start_at, booking.end_at = start, end
            booking.save(update_fields=["start_at", "end_at", "updated_at"])
            from .notifications import notify_booking
            notify_booking(booking, f"rescheduled-{booking.updated_at.timestamp()}", "A booking was rescheduled.", booking.service.provider.user, "rescheduled")
            notify_booking(booking, f"rescheduled-customer-{booking.updated_at.timestamp()}", "Your booking was rescheduled.", booking.customer, "rescheduled")
    except IntegrityError as exc:
        raise ValidationError("Sorry, this time slot has just been booked. Please select another available time.") from exc
    return booking

def transition(booking, status, actor):
    from accounts.models import User
    with transaction.atomic():
        _lock_provider_schedule(booking.provider_lock_id)
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        admin = actor.is_staff
        if actor == booking.customer:
            if status != Booking.Status.CANCELLED or booking.start_at - timezone.now() < timedelta(hours=2):
                raise ValidationError("You may cancel up to two hours before the appointment.")
        elif actor.role == User.Role.PROVIDER and actor == booking.service.provider.user:
            if status not in TRANSITIONS.get(booking.status, set()): raise ValidationError("That status change is not allowed.")
        elif not admin:
            raise ValidationError("You cannot update this booking.")
        if status not in TRANSITIONS.get(booking.status, set()): raise ValidationError("That status change is not allowed.")
        from django.utils import timezone as django_timezone
        booking.status = status
        stamp = django_timezone.now()
        fields = ["status", "updated_at"]
        timestamp_field = {Booking.Status.CONFIRMED: "accepted_at", Booking.Status.IN_PROGRESS: "started_at", Booking.Status.COMPLETED: "completed_at", Booking.Status.CANCELLED: "cancelled_at"}.get(status)
        if timestamp_field:
            setattr(booking, timestamp_field, stamp); fields.append(timestamp_field)
        booking.save(update_fields=fields)
        from .notifications import notify_booking
        email_event = {
            Booking.Status.CONFIRMED: "accepted", Booking.Status.REJECTED: "rejected",
            Booking.Status.IN_PROGRESS: "in_progress", Booking.Status.COMPLETED: "completed",
            Booking.Status.CANCELLED: "cancelled",
        }[status]
        notify_booking(booking, f"status-{status}", f"Booking {booking.reference} is now {booking.get_status_display().lower()}.", booking.customer, email_event)
        if status == Booking.Status.CANCELLED and actor == booking.customer:
            notify_booking(booking, "status-cancelled-provider", f"Booking {booking.reference} was cancelled by the customer.", booking.service.provider.user, "cancelled_by_customer")
        if status == Booking.Status.COMPLETED:
            notify_booking(booking, "review-eligible", "Your completed service is ready for a review.", booking.customer)
    return booking
