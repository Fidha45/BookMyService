from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from config.views import forbidden_response
from django.forms import formset_factory
from django.db import transaction
from django.utils import timezone
from .forms import RegisterForm, ProfileForm, ProviderProfileForm, AvailabilityForm, AvailabilityBlockForm
from .models import ProviderProfile, WeeklyAvailability, User, AvailabilityBlock

def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.role == User.Role.PROVIDER:
            ProviderProfile.objects.create(user=user, display_name=user.first_name or user.email.split("@")[0], location="")
            messages.info(request, "Complete your provider profile before publishing services.")
        login(request, user)
        return redirect("dashboard")
    return render(request, "form_page.html", {"form": form, "title": "Create your account"})

@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save(); messages.success(request, "Profile updated."); return redirect("profile")
    if request.user.role == User.Role.CUSTOMER:
        customer_location = request.user.bookings.exclude(service__location="").values_list("service__location", flat=True).first()
        return render(request, "accounts/customer_profile.html", {"form": form, "title": "My profile", "customer_location": customer_location})
    return render(request, "form_page.html", {"form": form, "title": "Your profile"})

@login_required
def provider_settings(request):
    if request.user.role != User.Role.PROVIDER:
        return forbidden_response(request)
    profile = request.user.provider_profile
    if request.method == "POST" and request.POST.get("action") == "add_block":
        block_form = AvailabilityBlockForm(request.POST)
        if block_form.is_valid():
            block = block_form.save(commit=False); block.provider = profile; block.save()
            messages.success(request, "Unavailable period added to your calendar.")
            return redirect("provider_settings")
    else: block_form = AvailabilityBlockForm()
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    existing = {row.weekday: row for row in profile.availability.all()}
    initial = [{"start_time": existing[d].start_time if d in existing else None, "end_time": existing[d].end_time if d in existing else None} for d in range(7)]
    DayFormSet = formset_factory(AvailabilityForm, extra=0)
    profile_data = request.POST if request.method == "POST" and request.POST.get("action") != "add_block" else None
    form = ProviderProfileForm(profile_data, request.FILES or None, instance=profile, prefix="profile")
    schedule = DayFormSet(profile_data, initial=initial, prefix="day")
    if request.method == "POST" and form.is_valid() and schedule.is_valid():
        with transaction.atomic():
            ProviderProfile.objects.select_for_update().get(pk=profile.pk)
            form.save()
            for day, day_form in enumerate(schedule.forms):
                start, end = day_form.cleaned_data.get("start_time"), day_form.cleaned_data.get("end_time")
                if start and end:
                    WeeklyAvailability.objects.update_or_create(provider=profile, weekday=day, defaults={"start_time": start, "end_time": end})
                else:
                    WeeklyAvailability.objects.filter(provider=profile, weekday=day).delete()
        messages.success(request, "Provider profile and weekly availability saved.")
        return redirect("provider_settings")
    rows = [{"name": weekdays[i], "form": schedule.forms[i]} for i in range(7)]
    return render(request, "accounts/provider_settings.html", {"form": form, "schedule": schedule, "availability_rows": rows, "block_form": block_form, "blocked_periods": profile.blocked_periods.filter(end_at__gte=timezone.now())})

@login_required
def remove_availability_block(request, pk):
    if request.method != "POST" or request.user.role != User.Role.PROVIDER: return forbidden_response(request)
    block = get_object_or_404(AvailabilityBlock, pk=pk, provider__user=request.user)
    block.delete(); messages.success(request, "Unavailable period removed.")
    return redirect("provider_settings")
