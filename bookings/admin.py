from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils import timezone
from .models import Booking, Notification, Payment, ProblemReport

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("admin_reference", "customer", "service", "provider_name", "start_at", "price_at_booking", "payment_status", "status")
    list_filter = ("status", "service", ("start_at", admin.DateFieldListFilter))
    search_fields = ("reference", "customer__email", "customer__first_name", "customer__last_name", "service__name", "service__provider__display_name")
    list_per_page = 8
    readonly_fields = tuple(field.name for field in Booking._meta.fields) + ("payment_summary", "timeline_summary")
    fieldsets = (
        ("Booking", {"fields": ("reference", "status", "customer", "service", "provider_lock")}),
        ("Appointment", {"fields": ("start_at", "end_at", "duration_at_booking", "price_at_booking")}),
        ("Payment", {"fields": ("payment_summary",)}),
        ("Booking timeline", {"fields": ("timeline_summary", "created_at", "accepted_at", "started_at", "completed_at", "cancelled_at", "updated_at")}),
        ("System identifiers", {"fields": ("id", "request_key")}),
    )
    # Completion is deliberately provider/customer controlled by transition();
    # exposing a staff action here only creates a bulk action that always fails.
    actions = ("confirm_bookings", "reject_bookings", "start_bookings", "cancel_bookings")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "customer", "service", "service__provider", "service__provider__user"
        ).prefetch_related("payments")

    @admin.display(description="Booking reference", ordering="reference")
    def admin_reference(self, obj):
        return f"#{str(obj.reference)[:12].upper()}"

    @admin.display(description="Service provider", ordering="service__provider__display_name")
    def provider_name(self, obj):
        return obj.service.provider.display_name

    @admin.display(description="Payment")
    def payment_status(self, obj):
        statuses = {payment.status for payment in obj.payments.all()}
        if Payment.Status.SUCCEEDED in statuses:
            return "Paid"
        if Payment.Status.FAILED in statuses:
            return "Failed"
        return "Pending" if statuses else "Not recorded"

    @admin.display(description="Payment details")
    def payment_summary(self, obj):
        payments = list(obj.payments.all())
        if not payments:
            return "No payment recorded"
        latest = max(payments, key=lambda payment: (payment.created_at, payment.pk))
        return f"{latest.get_status_display()} · {latest.currency} {latest.amount} · {latest.gateway} · {latest.gateway_payment_id or 'No transaction ID'}"

    @admin.display(description="Status history")
    def timeline_summary(self, obj):
        steps = [("Booking requested", obj.created_at), ("Provider accepted", obj.accepted_at), ("Service started", obj.started_at)]
        if obj.status == Booking.Status.AWAITING_CUSTOMER_CONFIRMATION:
            steps.append(("Provider marked the service complete; waiting for customer confirmation", obj.updated_at))
        if obj.completed_at:
            steps.append(("Customer confirmed completion", obj.completed_at))
        if obj.cancelled_at:
            steps.append(("Booking cancelled", obj.cancelled_at))
        return format_html("<ol class='bms-booking-admin-timeline'>{}</ol>", format_html_join("", "<li><strong>{}</strong><time>{}</time></li>", ((label, stamp.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ") if stamp else "Pending") for label, stamp in steps)))

    def _transition_selected(self, request, queryset, status, label):
        from .logic import transition
        changed, skipped = 0, 0
        for booking in queryset.select_related("provider_lock", "service__provider__user"):
            try:
                transition(booking, status, request.user)
                changed += 1
            except ValidationError:
                skipped += 1
        if changed:
            self.message_user(request, f"{changed} booking(s) {label}.", level="SUCCESS")
        if skipped:
            self.message_user(request, f"{skipped} booking(s) could not be updated because the transition is not valid.", level="WARNING")

    @admin.action(description="Confirm selected pending bookings")
    def confirm_bookings(self, request, queryset):
        return self._transition_selected(request, queryset, Booking.Status.CONFIRMED, "confirmed")

    @admin.action(description="Reject selected pending bookings")
    def reject_bookings(self, request, queryset):
        return self._transition_selected(request, queryset, Booking.Status.REJECTED, "rejected")

    @admin.action(description="Start selected confirmed bookings")
    def start_bookings(self, request, queryset):
        return self._transition_selected(request, queryset, Booking.Status.IN_PROGRESS, "started")

    @admin.action(description="Cancel selected eligible bookings")
    def cancel_bookings(self, request, queryset):
        return self._transition_selected(request, queryset, Booking.Status.CANCELLED, "cancelled")

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("booking", "amount", "currency", "status", "gateway", "verified_at")
    list_filter = ("status", "gateway", "currency")
    search_fields = ("booking__reference", "gateway_order_id", "gateway_payment_id")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "message", "created_at", "read_at")
    list_filter = ("created_at", "read_at")
    search_fields = ("recipient__email", "message", "event_key")

@admin.register(ProblemReport)
class ProblemReportAdmin(admin.ModelAdmin):
    list_display = ("booking_reference", "customer", "report_summary", "status", "reported_at", "resolved_at")
    list_filter = ("status", "reported_at")
    search_fields = ("booking__reference", "customer__email", "description", "resolution")
    readonly_fields = ("booking", "customer", "description", "reported_at", "resolved_at")
    fields = ("booking", "customer", "description", "status", "resolution", "reported_at", "resolved_at")
    ordering = ("status", "-reported_at")
    list_per_page = 8

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("booking", "customer", "booking__service")

    @admin.display(description="Booking", ordering="booking__reference")
    def booking_reference(self, obj):
        url = reverse("admin:bookings_booking_change", args=[obj.booking_id])
        return format_html('<a href="{}">#{}</a>', url, str(obj.booking.reference)[:12].upper())

    @admin.display(description="Reported problem")
    def report_summary(self, obj):
        return obj.description[:100]

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.status == ProblemReport.Status.RESOLVED:
            fields.extend(("status", "resolution"))
        return tuple(dict.fromkeys(fields))

    def save_model(self, request, obj, form, change):
        if obj.status == ProblemReport.Status.RESOLVED:
            obj.resolved_at = obj.resolved_at or timezone.now()
        else:
            obj.resolved_at = None
        super().save_model(request, obj, form, change)
