from django.conf import settings
from django.db import models
from django.db.models import Q
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields.ranges import RangeOperators
from django.db.models import F, Func, Value
from django.utils import timezone
from datetime import timedelta
import uuid
from services.models import Service

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING="pending", "Pending"
        CONFIRMED="confirmed", "Confirmed"
        IN_PROGRESS="in_progress", "In progress"
        COMPLETED="completed", "Completed"
        REJECTED="rejected", "Rejected"
        CANCELLED="cancelled", "Cancelled"
    OCCUPYING = (Status.PENDING, Status.CONFIRMED, Status.IN_PROGRESS)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    # Denormalized solely to let PostgreSQL enforce provider/time overlap with a
    # GiST exclusion constraint. It is populated from service.provider at create.
    provider_lock = models.ForeignKey("accounts.ProviderProfile", on_delete=models.PROTECT, related_name="booking_rows")
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    price_at_booking = models.DecimalField(max_digits=9, decimal_places=2)
    duration_at_booking = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    request_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    class Meta:
        ordering = ["-start_at"]
        indexes = [models.Index(fields=["start_at", "status"]), models.Index(fields=["customer", "status"]), models.Index(fields=["service", "status", "start_at", "end_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(start_at__lt=models.F("end_at")), name="booking_start_before_end"),
            ExclusionConstraint(
                name="exclude_overlapping_active_provider_bookings",
                expressions=[
                    ("provider_lock", RangeOperators.EQUAL),
                    (Func(F("start_at"), F("end_at"), Value("[)"), function="TSTZRANGE", output_field=DateTimeRangeField()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=("pending", "confirmed", "in_progress")),
            ),
        ]
    @property
    def provider(self): return self.service.provider
    @property
    def successful_payment(self):
        return self.payments.filter(status=Payment.Status.SUCCEEDED).first()
    @property
    def customer_can_cancel(self):
        return (
            self.status in (self.Status.PENDING, self.Status.CONFIRMED)
            and self.start_at - timezone.now() >= timedelta(hours=2)
        )
    @property
    def customer_can_reschedule(self):
        return (
            self.status in (self.Status.PENDING, self.Status.CONFIRMED)
            and self.start_at > timezone.now()
        )


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    event_key = models.CharField(max_length=180, unique=True)
    message = models.CharField(max_length=240)
    url = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "read_at", "created_at"])]


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=9, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED)
    gateway = models.CharField(max_length=20, default="razorpay")
    gateway_order_id = models.CharField(max_length=80, blank=True, unique=True, null=True)
    gateway_payment_id = models.CharField(max_length=80, blank=True, unique=True, null=True)
    # MySQL does not support partial unique indexes. A generated nullable key
    # keeps the active-payment uniqueness rule database-enforced on supported
    # backends: active rows contain booking_id, terminal rows contain NULL.
    active_booking_id = models.GeneratedField(
        expression=models.Case(
            models.When(status__in=("created", "pending", "succeeded"), then=F("booking_id")),
            default=Value(None, output_field=models.BigIntegerField()),
            output_field=models.BigIntegerField(),
        ),
        output_field=models.BigIntegerField(null=True),
        db_persist=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["active_booking_id"], name="one_active_payment_per_booking")]
