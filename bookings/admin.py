from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import Booking, Notification, Payment

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("reference", "customer", "service", "start_at", "status")
    list_filter = ("status", "start_at")
    search_fields = ("reference", "customer__email", "service__name")
    readonly_fields = tuple(field.name for field in Booking._meta.fields)
    actions = ("confirm_bookings", "reject_bookings", "start_bookings", "complete_bookings", "cancel_bookings")

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

    @admin.action(description="Complete selected in-progress bookings")
    def complete_bookings(self, request, queryset):
        return self._transition_selected(request, queryset, Booking.Status.COMPLETED, "completed")

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
