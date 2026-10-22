from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from config.views import forbidden_response
from django.forms import formset_factory
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.http import url_has_allowed_host_and_scheme
import unicodedata
import calendar
from datetime import date, timedelta
from urllib.parse import urlencode
from bookings.models import Booking
from bookings.logic import _lock_provider_schedule, available_slots
from services.models import Service
from .forms import RegisterForm, ProfileForm, ProviderProfileForm, AvailabilityForm, AvailabilityBlockForm
from .models import ProviderProfile, WeeklyAvailability, User, AvailabilityBlock

class RoleBasedLoginView(LoginView):
    def get_default_redirect_url(self):
        if self.request.user.role == User.Role.CUSTOMER:
            return reverse("service_list")
        return reverse("dashboard")

def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.role == User.Role.PROVIDER:
            ProviderProfile.objects.create(user=user, display_name=user.first_name or user.email.split("@")[0], location="")
            messages.info(request, "Complete your provider profile before publishing services.")
        login(request, user)
        return redirect("service_list" if user.role == User.Role.CUSTOMER else "dashboard")
    return render(request, "form_page.html", {"form": form, "title": "Create your account"})

@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Profile updated."); return redirect("profile")
    if request.user.role == User.Role.CUSTOMER:
        customer_location = request.user.bookings.exclude(service__location="").values_list("service__location", flat=True).first()
        return render(request, "accounts/customer_profile.html", {"form": form, "title": "My profile", "customer_location": customer_location, "active_nav": "profile"})
    return render(request, "form_page.html", {"form": form, "title": "Your profile"})

@login_required
def provider_location_update(request):
    if request.method != "POST" or request.user.role != User.Role.PROVIDER:
        return forbidden_response(request)
    profile = getattr(request.user, "provider_profile", None)
    if profile is None:
        return forbidden_response(request)

    raw_location = request.POST.get("location", "")
    location = " ".join(raw_location.split())
    if not location:
        messages.error(request, "Enter a service location before saving.")
    elif len(location) > ProviderProfile._meta.get_field("location").max_length:
        messages.error(request, "Location must be 120 characters or fewer.")
    elif any(unicodedata.category(char) == "Cc" for char in raw_location):
        messages.error(request, "Location cannot contain control characters.")
    else:
        profile.location = location
        profile.save(update_fields=["location"])
        messages.success(request, "Service location updated.")

    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse("dashboard")
    return redirect(next_url)

@login_required
def provider_settings(request):
    if request.user.role != User.Role.PROVIDER:
        return forbidden_response(request)
    profile = request.user.provider_profile
    action = request.POST.get("action", "") if request.method == "POST" else ""
    if request.method == "POST" and action == "add_block":
        block_form = AvailabilityBlockForm(request.POST)
        if block_form.is_valid():
            block = block_form.save(commit=False); block.provider = profile
            try:
                with transaction.atomic():
                    _lock_provider_schedule(profile.pk)
                    conflict = Booking.objects.filter(
                        provider_lock=profile, status__in=Booking.OCCUPYING,
                        start_at__lt=block.end_at, end_at__gt=block.start_at,
                    ).exists()
                    if conflict:
                        raise ValidationError("This unavailable period overlaps an existing booking.")
                    block.save()
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, "Unavailable period added to your calendar.")
            return redirect("provider_settings")
    else: block_form = AvailabilityBlockForm()
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    existing = {row.weekday: row for row in profile.availability.all()}
    initial = [{"start_time": existing[d].start_time if d in existing else None, "end_time": existing[d].end_time if d in existing else None} for d in range(7)]
    DayFormSet = formset_factory(AvailabilityForm, extra=0)
    profile_data = request.POST if request.method == "POST" and action not in ("add_block", "save_availability") else None
    form = ProviderProfileForm(profile_data, request.FILES or None, instance=profile, prefix="profile")
    schedule_data = request.POST if request.method == "POST" and action != "add_block" else None
    schedule = DayFormSet(schedule_data, initial=initial, prefix="day")
    if request.method == "POST" and action == "save_availability" and schedule.is_valid():
        proposed_hours = {
            day: (row.cleaned_data.get("start_time"), row.cleaned_data.get("end_time"))
            for day, row in enumerate(schedule.forms)
        }
        conflict = False
        with transaction.atomic():
            _lock_provider_schedule(profile.pk)
            active_bookings = Booking.objects.filter(
                provider_lock=profile, status__in=Booking.OCCUPYING, end_at__gt=timezone.now()
            ).only("start_at", "end_at")
            for booking in active_bookings:
                start, end = timezone.localtime(booking.start_at), timezone.localtime(booking.end_at)
                hours = proposed_hours.get(start.weekday())
                if not hours or not hours[0] or not hours[1] or start.time() < hours[0] or end.time() > hours[1] or start.date() != end.date():
                    conflict = True
                    break
            if not conflict:
                for day, (start, end) in proposed_hours.items():
                    if start and end:
                        WeeklyAvailability.objects.update_or_create(provider=profile, weekday=day, defaults={"start_time": start, "end_time": end})
                    else:
                        WeeklyAvailability.objects.filter(provider=profile, weekday=day).delete()
        if conflict:
            messages.error(request, "Your new working hours would conflict with an existing booking. Keep the booked appointment within your availability.")
        else:
            messages.success(request, "Weekly availability hours saved.")
            query = {key: request.POST.get(key, "") for key in ("date", "service") if request.POST.get(key)}
            query_string = urlencode({"section": "availability", **query})
            return redirect(f"{reverse('provider_settings')}?{query_string}#weekly-hours")
    elif request.method == "POST" and action not in ("add_block", "save_availability") and form.is_valid() and schedule.is_valid():
        proposed_hours = {
            day: (row.cleaned_data.get("start_time"), row.cleaned_data.get("end_time"))
            for day, row in enumerate(schedule.forms)
        }
        conflict = False
        with transaction.atomic():
            _lock_provider_schedule(profile.pk)
            active_bookings = Booking.objects.filter(
                provider_lock=profile, status__in=Booking.OCCUPYING, end_at__gt=timezone.now()
            ).only("start_at", "end_at")
            for booking in active_bookings:
                start, end = timezone.localtime(booking.start_at), timezone.localtime(booking.end_at)
                hours = proposed_hours.get(start.weekday())
                if not hours or not hours[0] or not hours[1] or start.time() < hours[0] or end.time() > hours[1] or start.date() != end.date():
                    conflict = True
                    break
            if not conflict:
                form.save()
                for day, (start, end) in proposed_hours.items():
                    if start and end:
                        WeeklyAvailability.objects.update_or_create(provider=profile, weekday=day, defaults={"start_time": start, "end_time": end})
                    else:
                        WeeklyAvailability.objects.filter(provider=profile, weekday=day).delete()
        if conflict:
            messages.error(request, "Your new working hours would conflict with an existing booking. Keep the booked appointment within your availability.")
        else:
            messages.success(request, "Provider profile and weekly availability saved.")
            return redirect("provider_settings")
    rows = [{"name": weekdays[i], "form": schedule.forms[i]} for i in range(7)]
    services = Service.objects.filter(provider=profile).select_related("category").order_by("name")
    selected_date = timezone.localdate()
    try:
        if request.GET.get("date"):
            selected_date = date.fromisoformat(request.GET["date"])
    except (ValueError, TypeError):
        pass
    selected_service = services.filter(pk=request.GET.get("service")).first() if request.GET.get("service", "").isdigit() else None
    selected_service = selected_service or services.first()
    available = available_slots(selected_service, selected_date) if selected_service else []
    booked_rows = Booking.objects.filter(
        provider_lock=profile, status__in=Booking.OCCUPYING, start_at__date=selected_date
    ).select_related("service", "customer").order_by("start_at")
    calendar_slots = []
    if selected_service:
        duration = timedelta(minutes=selected_service.duration_minutes)
        calendar_slots.extend({"start": slot, "end": slot + duration, "status": "available"} for slot in available)
    calendar_slots.extend({"start": booking.start_at, "end": booking.end_at, "status": "booked", "booking": booking} for booking in booked_rows)
    calendar_slots.sort(key=lambda slot: slot["start"])
    month_start = selected_date.replace(day=1)
    previous_month = (month_start - timedelta(days=1)).replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    context = {
        "form": form, "schedule": schedule, "availability_rows": rows, "block_form": block_form,
        "blocked_periods": profile.blocked_periods.filter(end_at__gte=timezone.now()),
        "provider_services": services, "selected_service": selected_service,
        "selected_date": selected_date, "available_slots": available, "booked_slots": booked_rows,
        "calendar_weeks": calendar.Calendar(firstweekday=6).monthdatescalendar(selected_date.year, selected_date.month),
        "previous_month": previous_month, "next_month": next_month, "calendar_slots": calendar_slots,
        "availability_page": request.GET.get("section") == "availability",
        "availability_form_submitted": request.method == "POST" and action == "save_availability",
    }
    template = "accounts/provider_availability.html" if context["availability_page"] else "accounts/provider_settings.html"
    return render(request, template, context)

@login_required
def remove_availability_block(request, pk):
    if request.method != "POST" or request.user.role != User.Role.PROVIDER: return forbidden_response(request)
    block = get_object_or_404(AvailabilityBlock, pk=pk, provider__user=request.user)
    with transaction.atomic():
        _lock_provider_schedule(block.provider_id)
        block.delete()
    messages.success(request, "Unavailable period removed.")
    return redirect("provider_settings")
