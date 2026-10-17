from datetime import date, datetime, timedelta
import calendar
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseNotAllowed
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from config.views import forbidden_response
from accounts.models import ProviderProfile, User
from bookings.models import Booking
from .forms import ServiceForm
from .models import Category, Favourite, Service

def service_list(request, explore=False):
    qs = Service.objects.filter(is_active=True, provider__user__is_active=True).select_related("provider", "provider__user", "category").annotate(
        rating=Avg("bookings__review__rating"),
        review_count=Count("bookings__review", distinct=True),
        booking_count=Count("bookings", distinct=True),
    )
    q = request.GET.get("q", "").strip()
    if q: qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q) | Q(provider__display_name__icontains=q))
    selected_categories = [slug for slug in request.GET.getlist("category") if slug]
    if selected_categories: qs = qs.filter(category__slug__in=selected_categories)
    if request.GET.get("provider"):
        try: qs = qs.filter(provider_id=int(request.GET["provider"]))
        except ValueError: pass
    if request.GET.get("location"): qs = qs.filter(location__icontains=request.GET["location"])
    for field, lookup in (("min_price", "price__gte"), ("max_price", "price__lte")):
        if request.GET.get(field):
            try: qs = qs.filter(**{lookup: request.GET[field]})
            except (ValueError, TypeError): pass
    if request.GET.get("rating"):
        try: qs = qs.filter(rating__gte=float(request.GET["rating"]))
        except ValueError: pass
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    if request.GET.get("weekday"):
        try:
            weekday = int(request.GET["weekday"])
            if 0 <= weekday <= 6: qs = qs.filter(provider__availability__weekday=weekday).distinct()
        except ValueError: pass
    sort_options = {
        "popular": ("-booking_count", "-rating", "name", "pk"),
        "rating": ("-rating", "-review_count", "name", "pk"),
        "price_low": ("price", "name", "pk"),
        "price_high": ("-price", "name", "pk"),
        "newest": ("-created_at", "pk"),
    }
    sort_by = request.GET.get("sort", "popular")
    if sort_by not in sort_options: sort_by = "popular"
    page = Paginator(qs.order_by(*sort_options[sort_by]), 12 if explore else 9).get_page(request.GET.get("page"))
    categories = Category.objects.annotate(active_count=Count("services", filter=Q(services__is_active=True, services__provider__user__is_active=True))).filter(active_count__gt=0).order_by("name")
    illustrated_categories = {"home-cleaning", "plumbing", "electrical", "appliance-repair", "beauty-wellness", "painting", "moving-packing", "gardening"}
    category_artwork_files = {
        "home-cleaning": "home-cleaning.webp",
        "plumbing": "plumbing.webp",
        "electrical": "electrical.webp",
        "appliance-repair": "appliance-repair.webp",
        "beauty-wellness": "beauty-wellness.png",
        "painting": "painting.webp",
        "moving-packing": "moving-packing.webp",
        "gardening": "gardening.webp",
    }
    category_artwork = {
        slug: static(f"images/categories/{category_artwork_files[slug]}")
        for slug in illustrated_categories
    }
    for category in categories:
        category.artwork_url = category_artwork.get(category.slug)
    providers = ProviderProfile.objects.filter(user__is_active=True, services__is_active=True).distinct().order_by("display_name")
    featured = list(Service.objects.filter(is_active=True, provider__user__is_active=True).select_related("provider", "category").annotate(rating=Avg("bookings__review__rating"), booking_count=Count("bookings")).order_by("-booking_count", "-rating", "name")[:6])
    for service in featured:
        service.category.artwork_url = category_artwork.get(service.category.slug)
    for service in page.object_list:
        service.category.artwork_url = category_artwork.get(service.category.slug)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    layout_queries = {}
    for view_mode in ("grid", "list"):
        layout_params = query_params.copy()
        layout_params["view"] = view_mode
        layout_queries[view_mode] = layout_params.urlencode()
    from reviews.models import Review
    latest_reviews = Review.objects.filter(booking__service__is_active=True, booking__service__provider__user__is_active=True).exclude(text="").select_related("customer", "booking__service").order_by("-created_at")[:2]
    stats = {
        "providers": ProviderProfile.objects.filter(user__is_active=True).count(),
        "verified_providers": ProviderProfile.objects.filter(user__is_active=True, is_verified=True).count(),
        "services": Service.objects.filter(is_active=True, provider__user__is_active=True).count(),
        "reviews": Review.objects.filter(booking__service__is_active=True, booking__service__provider__user__is_active=True).count(),
    }
    context = {
        "page": page, "categories": categories, "providers": providers, "weekdays": weekdays,
        "filters": request.GET, "selected_categories": selected_categories,
        "featured": featured, "latest_reviews": latest_reviews,
        "stats": stats, "query_string": query_params.urlencode(),
        "sort_by": sort_by, "layout": request.GET.get("view") if request.GET.get("view") in {"grid", "list"} else "grid",
        "layout_queries": layout_queries,
        "locations": Service.objects.filter(is_active=True, provider__user__is_active=True).values_list("location", flat=True).distinct().order_by("location"),
        "price_bounds": Service.objects.filter(is_active=True, provider__user__is_active=True).aggregate(min=Min("price"), max=Max("price")),
    }
    if request.user.is_authenticated and request.user.role == User.Role.CUSTOMER:
        context["favourited_service_ids"] = set(Favourite.objects.filter(customer=request.user, service__isnull=False).values_list("service_id", flat=True))
    return render(request, "services/explore.html" if explore else "services/list.html", context)


def explore_services(request):
    return service_list(request, explore=True)

def service_detail(request, pk):
    service = get_object_or_404(Service.objects.select_related("provider", "provider__user", "category"), pk=pk)
    if (not service.is_active or not service.provider.user.is_active) and not (request.user.is_authenticated and (request.user.is_staff or request.user == service.provider.user)):
        from django.http import Http404
        raise Http404
    from reviews.models import Review
    reviews = Review.objects.filter(booking__service=service).select_related("customer").order_by("-created_at")
    average_rating = reviews.aggregate(value=Avg("rating"))["value"]
    from django.db.models import Count
    review_total = reviews.count()
    rating_counts = {row["rating"]: row["count"] for row in reviews.values("rating").annotate(count=Count("id"))}
    rating_distribution = [
        {"rating": score, "count": rating_counts.get(score, 0), "percent": round(rating_counts.get(score, 0) * 100 / review_total) if review_total else 0}
        for score in range(5, 0, -1)
    ]
    availability = service.provider.availability.order_by("weekday")
    provider_services = service.provider.services.filter(
        is_active=True, provider__user__is_active=True
    ).select_related("category").order_by("name", "pk")
    provider_reviews = Review.objects.filter(booking__service__provider=service.provider)
    provider_average_rating = provider_reviews.aggregate(value=Avg("rating"))["value"]
    provider_review_count = provider_reviews.count()
    related_services = Service.objects.filter(
        is_active=True, provider__user__is_active=True,
    ).filter(
        Q(category=service.category) | Q(location__iexact=service.location),
    ).exclude(pk=service.pk).select_related(
        "provider", "category",
    ).annotate(
        rating=Avg("bookings__review__rating"),
    ).order_by(
        "-rating", "name", "pk",
    ).distinct()[:3]
    # The catalog images are deliberately mapped to the files already in static/images/services.
    # No generated or category-mismatched placeholder photography is introduced.
    service_artwork = {
        "ac-service": "Ac repair.jpg", "ac-repair": "Ac repair.jpg",
        "appliance-repair": "Appliance repair.jpg", "carpentry": "Carpentry.jpg",
        "electrical": "Electrical work.jpg", "electrical-work": "Electrical work.jpg",
        "home-renovation": "Home renovation.jpg", "house-cleaning": "House cleaning.jpg",
        "home-cleaning": "House cleaning.jpg", "painting": "Painting.jpg",
        "pest-control": "pest control.jpg", "plumbing": "plumbing.png",
    }
    category_key = service.category.slug.lower().replace("_", "-")
    artwork_name = service_artwork.get(category_key)
    static_image_url = static(f"images/services/{artwork_name}") if artwork_name else None
    gallery_images = []
    if static_image_url:
        gallery_images.append({"url": static_image_url, "alt": f"{service.name} service"})
    if service.image:
        uploaded_url = service.image.url
        if not gallery_images or uploaded_url != gallery_images[0]["url"]:
            gallery_images.append({"url": uploaded_url, "alt": f"{service.name} provided by {service.provider.display_name}"})
    provider_service_count = service.provider.services.filter(is_active=True).count()

    # Show only dates and start times that pass the same live schedule, booking,
    # and provider-block checks used by the booking workflow.
    from bookings.logic import available_slots
    today = timezone.localdate()
    month_value = request.GET.get("month", "")
    try:
        year, month = (int(part) for part in month_value.split("-", 1))
        calendar_month = date(year, month, 1)
    except (ValueError, TypeError):
        calendar_month = today.replace(day=1)
    selected_day = today
    try:
        selected_day = date.fromisoformat(request.GET.get("date", ""))
    except (ValueError, TypeError):
        pass
    if request.GET.get("date"):
        calendar_month = selected_day.replace(day=1)
    elif calendar_month != today.replace(day=1):
        selected_day = calendar_month
    last_day = calendar.monthrange(calendar_month.year, calendar_month.month)[1]
    selected_slots = available_slots(service, selected_day) if selected_day.month == calendar_month.month and selected_day.year == calendar_month.year else []
    days_with_slots = {}
    for day_number in range(1, last_day + 1):
        day = calendar_month.replace(day=day_number)
        if day >= today:
            days_with_slots[day] = selected_slots if day == selected_day else available_slots(service, day)
    start_offset = calendar_month.weekday()
    calendar_start = calendar_month - timedelta(days=start_offset)
    calendar_weeks = []
    for week_index in range(6):
        week = []
        for day_offset in range(7):
            day = calendar_start + timedelta(days=week_index * 7 + day_offset)
            week.append({"date": day, "in_month": day.month == calendar_month.month, "available": bool(days_with_slots.get(day))})
        calendar_weeks.append(week)
    if selected_day.month != calendar_month.month or selected_day.year != calendar_month.year:
        selected_slots = []
    previous_month = (calendar_month.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (calendar_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    selected_start = request.GET.get("start_at", "")
    if not any(slot.strftime("%Y-%m-%dT%H:%M") == selected_start for slot in selected_slots):
        selected_start = ""

    for item in related_services:
        item_key = item.category.slug.lower().replace("_", "-")
        item_artwork = service_artwork.get(item_key)
        item.card_image_url = static(f"images/services/{item_artwork}") if item_artwork else (item.image.url if item.image else None)
    is_favourite = request.user.is_authenticated and Favourite.objects.filter(customer=request.user, service=service).exists()
    provider_is_favourite = request.user.is_authenticated and Favourite.objects.filter(customer=request.user, provider=service.provider).exists()
    return render(request, "services/detail.html", {"service": service, "reviews": reviews, "average_rating": average_rating, "rating_distribution": rating_distribution, "availability": availability, "provider_services": provider_services, "provider_service_count": provider_service_count, "provider_average_rating": provider_average_rating, "provider_review_count": provider_review_count, "related_services": related_services, "is_favourite": is_favourite, "provider_is_favourite": provider_is_favourite,
        "gallery_images": gallery_images, "calendar_month": calendar_month, "previous_month": previous_month, "next_month": next_month, "calendar_weeks": calendar_weeks, "selected_day": selected_day, "selected_slots": selected_slots, "selected_start": selected_start})


@login_required
def favourite_toggle(request, kind, pk):
    if request.method != "POST" or request.user.role != User.Role.CUSTOMER:
        return forbidden_response(request)
    if kind == "service":
        target = get_object_or_404(Service, pk=pk)
        lookup = {"customer": request.user, "service": target}
        back = request.POST.get("next") or "service_list"
    elif kind == "provider":
        target = get_object_or_404(ProviderProfile, pk=pk)
        lookup = {"customer": request.user, "provider": target}
        back = request.POST.get("next") or "service_list"
    else: return forbidden_response(request)
    # Serialize concurrent toggles for one customer so add/remove operations
    # retain their intended toggle behavior on every supported database.
    from django.db import transaction
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        favourite = Favourite.objects.filter(**lookup).first()
        if favourite:
            favourite.delete()
            messages.info(request, "Removed from favourites.")
        else:
            Favourite.objects.create(**lookup)
            messages.success(request, "Added to favourites.")
    from django.utils.http import url_has_allowed_host_and_scheme
    if back.startswith("/") and url_has_allowed_host_and_scheme(back, {request.get_host()}): return redirect(back)
    return redirect(back if back in ("service_list", "favourites") else "service_list")


@login_required
def favourites(request):
    if request.user.role != User.Role.CUSTOMER: return forbidden_response(request)
    rows = Favourite.objects.filter(customer=request.user).select_related("service__provider__user", "service__category", "provider__user")
    return render(request, "services/favourites.html", {"favourites": rows})


def match_services(request):
    from datetime import date, datetime, time as datetime_time
    from decimal import Decimal, InvalidOperation
    from bookings.logic import available_slots
    qs = Service.objects.filter(is_active=True, provider__user__is_active=True).select_related("provider__user", "category").annotate(rating=Avg("bookings__review__rating"), review_count=Count("bookings__review"))
    q = request.GET.get("q", "").strip()
    location = request.GET.get("location", "").strip()
    if q: qs = qs.filter(Q(name__icontains=q) | Q(category__name__icontains=q) | Q(description__icontains=q))
    if location: qs = qs.filter(Q(location__icontains=location) | Q(provider__location__icontains=location))
    if request.GET.get("category"): qs = qs.filter(category__slug=request.GET["category"])
    if request.GET.get("max_price"):
        try: qs = qs.filter(price__lte=Decimal(request.GET["max_price"]))
        except InvalidOperation: pass
    max_price = None
    if request.GET.get("max_price"):
        try: max_price = Decimal(request.GET["max_price"])
        except InvalidOperation: pass
    candidates = list(qs.order_by("-rating", "-review_count", "price", "name", "pk"))
    chosen = None
    if request.GET.get("date") and request.GET.get("start_at"):
        try:
            day = date.fromisoformat(request.GET["date"])
            local_time = datetime_time.fromisoformat(request.GET["start_at"])
            chosen = timezone.make_aware(datetime.combine(day, local_time), timezone.get_current_timezone())
        except ValueError: chosen = None
        if chosen:
            candidates = [service for service in candidates if any(slot.replace(second=0, microsecond=0) == chosen.replace(second=0, microsecond=0) for slot in available_slots(service, day))]
    # A transparent score built only from facts the catalog already knows.
    # Dimensions the customer did not ask for are omitted from the denominator.
    for service in candidates:
        reasons = []
        points = []
        if location:
            reasons.append("Location matches your search")
            points.append(100)
        if max_price is not None:
            reasons.append("Within your budget")
            points.append(100 if service.price <= max_price else 0)
        if chosen:
            reasons.append("Available at your selected time")
            points.append(100)
        trust = 50
        if service.provider.is_verified:
            trust += 25
        if service.rating:
            trust += (float(service.rating) / 5) * 25
            reasons.append(f"Rated {service.rating:.1f} from {service.review_count} review{'s' if service.review_count != 1 else ''}")
        elif service.provider.is_verified:
            reasons.append("Provider verified")
        else:
            reasons.append("New provider · no reviews yet")
        points.append(trust)
        service.fit_score = round(sum(points) / len(points))
        service.fit_reasons = reasons
    candidates.sort(key=lambda service: (-service.fit_score, -(service.rating or 0), -service.review_count, service.price, service.name, service.pk))
    return render(request, "services/matches.html", {"matches": candidates, "categories": Category.objects.order_by("name"), "filters": request.GET, "time_filter": bool(chosen)})

@login_required
def dashboard(request):
    if request.user.is_staff:
        from bookings.models import Notification
        query = request.GET.get("q", "").strip()[:100]
        booking_status = request.GET.get("booking_status", "all")
        if booking_status not in {"all", *Booking.Status.values}:
            booking_status = "all"
        user_type = request.GET.get("user_type", "all")
        if user_type not in {"all", User.Role.CUSTOMER, User.Role.PROVIDER}:
            user_type = "all"
        approval_size = request.GET.get("approval_size", "5")
        if approval_size not in {"5", "25", "100"}:
            approval_size = "5"

        customer_users = User.objects.filter(role=User.Role.CUSTOMER)
        provider_users = User.objects.filter(role=User.Role.PROVIDER)
        visible_users = User.objects.filter(role__in=[User.Role.CUSTOMER, User.Role.PROVIDER]).order_by("-date_joined", "-pk")
        if user_type != "all":
            visible_users = visible_users.filter(role=user_type)
        if query:
            name_query = Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
            visible_users = visible_users.filter(name_query)

        booking_rows = Booking.objects.select_related(
            "customer", "service", "service__provider", "service__provider__user"
        ).order_by("-created_at", "-pk")
        if booking_status != "all":
            booking_rows = booking_rows.filter(status=booking_status)
        if query:
            booking_search = (
                Q(customer__first_name__icontains=query)
                | Q(customer__last_name__icontains=query)
                | Q(customer__email__icontains=query)
                | Q(service__name__icontains=query)
                | Q(service__provider__display_name__icontains=query)
            )
            try:
                from uuid import UUID
                booking_search |= Q(reference=UUID(query))
            except (ValueError, TypeError, AttributeError):
                pass
            booking_rows = booking_rows.filter(booking_search)

        service_matches = Service.objects.select_related("category", "provider").order_by("name")
        if query:
            service_matches = service_matches.filter(
                Q(name__icontains=query) | Q(category__name__icontains=query)
                | Q(provider__display_name__icontains=query)
            )

        active_providers = ProviderProfile.objects.filter(
            user__role=User.Role.PROVIDER, user__is_active=True
        )
        pending_providers = active_providers.filter(
            approval_status=ProviderProfile.ApprovalStatus.PENDING
        ).select_related("user").order_by("user__date_joined", "pk")
        pending_approval_count = pending_providers.count()

        booking_page = Paginator(booking_rows, 8).get_page(request.GET.get("booking_page", 1))
        user_page = Paginator(visible_users, 8).get_page(request.GET.get("user_page", 1))
        pending_page = Paginator(pending_providers, int(approval_size)).get_page(request.GET.get("approval_page", 1))

        customers_count = customer_users.count()
        providers_count = provider_users.count()
        user_total = customers_count + providers_count
        categories = list(Category.objects.annotate(
            service_count=Count("services", filter=Q(services__is_active=True))
        ).order_by("-service_count", "name")[:6])
        category_peak = max((row.service_count for row in categories), default=0)
        for category in categories:
            category.percent = round(category.service_count * 100 / category_peak) if category_peak else 0

        unread_notification_count = Notification.objects.filter(recipient=request.user, read_at__isnull=True).count()

        data = {
            "total_users": user_total,
            "customers": customers_count,
            "providers": providers_count,
            "verified_providers": active_providers.filter(approval_status=ProviderProfile.ApprovalStatus.APPROVED).count(),
            "unverified_providers": active_providers.exclude(approval_status=ProviderProfile.ApprovalStatus.APPROVED).count(),
            "pending_approvals": pending_approval_count,
            "services": Service.objects.filter(is_active=True).count(),
            "total_services": Service.objects.count(),
            "total": Booking.objects.count(),
            "pending": Booking.objects.filter(status=Booking.Status.PENDING).count(),
            "completed": Booking.objects.filter(status=Booking.Status.COMPLETED).count(),
            "cancelled": Booking.objects.filter(status=Booking.Status.CANCELLED).count(),
            "categories": categories,
        }
        return render(request, "dashboard/admin.html", {
            "stats": data,
            "query": query,
            "booking_status": booking_status,
            "user_type": user_type,
            "approval_size": approval_size,
            "booking_statuses": Booking.Status.choices,
            "booking_page": booking_page,
            "user_page": user_page,
            "pending_page": pending_page,
        "service_matches": service_matches[:5] if query else [],
        "can_manage_accounts": request.user.has_perm("accounts.change_user"),
            "user_share": round(customers_count * 100 / user_total) if user_total else 0,
            "unread_notification_count": unread_notification_count,
        })
    if request.user.role == User.Role.PROVIDER:
        from bookings.models import Notification
        from reviews.models import Review

        booking_records = Booking.objects.filter(service__provider__user=request.user).select_related("service", "customer").order_by("-created_at", "-pk")
        services = Service.objects.filter(provider__user=request.user).select_related("category").order_by("-created_at", "-pk")
        completed_bookings = booking_records.filter(status=Booking.Status.COMPLETED, completed_at__isnull=False)
        today = timezone.localdate()
        month_start = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()))
        month_end_date = today.replace(day=28) + timedelta(days=4)
        month_end = timezone.make_aware(datetime.combine(month_end_date.replace(day=1), datetime.min.time()))
        query = request.GET.get("q", "").strip()[:100]
        booking_status = request.GET.get("booking_status", "all")
        if booking_status not in {"all", *Booking.Status.values}:
            booking_status = "all"
        visible_bookings = booking_records
        visible_services = services
        if booking_status != "all":
            visible_bookings = visible_bookings.filter(status=booking_status)
        if query:
            visible_bookings = visible_bookings.filter(
                Q(customer__first_name__icontains=query) | Q(customer__last_name__icontains=query)
                | Q(customer__email__icontains=query) | Q(service__name__icontains=query)
                | Q(service__category__name__icontains=query)
            )
            visible_services = visible_services.filter(
                Q(name__icontains=query) | Q(category__name__icontains=query) | Q(location__icontains=query)
            )
        # Keep recent requests and history as separate dashboard panels while
        # keeping all counts and earnings based on the provider's full records.
        recent_requests = booking_records.filter(status=Booking.Status.PENDING)[:5]
        booking_history = booking_records.exclude(status=Booking.Status.PENDING)[:5]
        availability_rows = list(request.user.provider_profile.availability.order_by("weekday"))
        availability_by_day = {row.weekday: row for row in availability_rows}
        weekdays = [{"name": name, "row": availability_by_day.get(index)} for index, name in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))]
        months = []
        cursor = (today.replace(day=1) - timedelta(days=150)).replace(day=1)
        for _ in range(6):
            next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            start = timezone.make_aware(datetime.combine(cursor, datetime.min.time()))
            end = timezone.make_aware(datetime.combine(next_month, datetime.min.time()))
            amount = completed_bookings.filter(completed_at__gte=start, completed_at__lt=end).aggregate(total=Sum("price_at_booking"))["total"] or 0
            months.append({"label": cursor.strftime("%b"), "amount": amount})
            cursor = next_month
        peak = max((row["amount"] for row in months), default=0)
        for row in months:
            row["percent"] = int(row["amount"] * 100 / peak) if peak else 0
        notifications = Notification.objects.filter(recipient=request.user, read_at__isnull=True)
        return render(request, "dashboard/provider.html", {
            "bookings": visible_bookings[:10], "services": visible_services,
            "recent_requests": recent_requests, "booking_history": booking_history,
            "availability_by_day": availability_by_day,
            "weekdays": weekdays,
            "reviews": Review.objects.filter(booking__service__provider__user=request.user).select_related("customer", "booking__service").order_by("-created_at")[:4],
            "query": query, "booking_status": booking_status,
            "notifications": notifications[:5], "unread_notification_count": notifications.count(),
            "earnings_months": months,
            "estimated_earnings": completed_bookings.aggregate(total=Sum("price_at_booking"))["total"] or 0,
            "estimated_month_earnings": completed_bookings.filter(completed_at__gte=month_start, completed_at__lt=month_end).aggregate(total=Sum("price_at_booking"))["total"] or 0,
            "pending_count": booking_records.filter(status=Booking.Status.PENDING).count(),
            "confirmed_count": booking_records.filter(status=Booking.Status.CONFIRMED).count(),
            "completed_count": completed_bookings.count(),
            "active_service_count": services.filter(is_active=True).count(),
            "in_progress_count": booking_records.filter(status=Booking.Status.IN_PROGRESS).count(),
            "cancelled_count": booking_records.filter(status=Booking.Status.CANCELLED).count(),
        })
    bookings = Booking.objects.filter(customer=request.user).select_related("service", "service__provider", "service__category", "service__provider__user").order_by("-start_at")
    upcoming = bookings.filter(start_at__gte=timezone.now(), status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED))
    history = bookings.exclude(status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED))
    recent_bookings = bookings.exclude(status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED))[:3]
    page_view = request.GET.get("view", "dashboard")
    booking_view = page_view == "bookings"
    review_view = page_view == "reviews"
    selected_status = request.GET.get("status", "all")
    if selected_status == "upcoming":
        visible_bookings = upcoming
    elif selected_status == "history":
        visible_bookings = history
    elif selected_status in {Booking.Status.COMPLETED, Booking.Status.CANCELLED}:
        visible_bookings = bookings.filter(status=selected_status)
    else:
        selected_status = "all"
        visible_bookings = bookings
    from bookings.models import Notification
    from reviews.models import Review
    return render(request, "dashboard/customer.html", {
        "bookings": bookings, "upcoming_bookings": upcoming, "history_bookings": history,
        "recent_bookings": recent_bookings, "upcoming_count": upcoming.count(),
        "visible_bookings": visible_bookings, "booking_view": booking_view, "review_view": review_view, "selected_status": selected_status,
        "customer_reviews": Review.objects.filter(customer=request.user).select_related("booking__service", "booking__service__provider").order_by("-created_at"),
        "customer_location": bookings.exclude(service__location="").values_list("service__location", flat=True).first(),
        "favourite_count": Favourite.objects.filter(customer=request.user).count(),
        "pending_count": bookings.filter(status=Booking.Status.PENDING).count(),
        "confirmed_count": bookings.filter(status=Booking.Status.CONFIRMED).count(),
        "completed_count": bookings.filter(status=Booking.Status.COMPLETED).count(),
        "notifications": Notification.objects.filter(recipient=request.user, read_at__isnull=True)[:5],
    })


@login_required
def admin_account_status(request, pk, action):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_staff or not request.user.has_perm("accounts.change_user"):
        return forbidden_response(request)
    if action not in {"activate", "deactivate"}:
        return forbidden_response(request)
    if request.user.pk == pk and action == "deactivate":
        messages.error(request, "You cannot deactivate your own administrator account.")
        return redirect(f"{reverse('dashboard')}#recent-users")

    with transaction.atomic():
        account = get_object_or_404(
            User.objects.select_for_update(),
            pk=pk,
            role__in=(User.Role.CUSTOMER, User.Role.PROVIDER),
            is_staff=False,
        )
        account.is_active = action == "activate"
        account.save(update_fields=["is_active"])

    verb = "activated" if action == "activate" else "deactivated"
    messages.success(request, f"{account.get_role_display()} account {account.email} was {verb}.")
    return redirect(f"{reverse('dashboard')}#recent-users")


@login_required
def admin_provider_review(request, pk, action):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_staff or not request.user.has_perm("accounts.change_providerprofile"):
        return forbidden_response(request)
    status_by_action = {
        "approve": ProviderProfile.ApprovalStatus.APPROVED,
        "reject": ProviderProfile.ApprovalStatus.REJECTED,
    }
    if action not in status_by_action:
        return forbidden_response(request)

    with transaction.atomic():
        provider = get_object_or_404(
            ProviderProfile.objects.select_for_update().select_related("user"),
            pk=pk,
            user__role=User.Role.PROVIDER,
        )
        provider.approval_status = status_by_action[action]
        provider.is_verified = action == "approve"
        provider.approval_reviewed_at = timezone.now()
        provider.save(update_fields=["approval_status", "is_verified", "approval_reviewed_at"])

    if action == "approve":
        messages.success(request, f"{provider.display_name} was approved and verified.")
    else:
        messages.success(request, f"{provider.display_name} was marked as rejected. Their account and services were left unchanged.")
    return redirect(f"{reverse('dashboard')}#provider-approvals")


@login_required
def provider_earnings(request):
    if request.user.role != User.Role.PROVIDER or not request.user.is_active:
        return forbidden_response(request)
    completed = Booking.objects.filter(
        service__provider__user=request.user,
        status=Booking.Status.COMPLETED,
        completed_at__isnull=False,
    )
    today = timezone.localdate()
    month_start = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()))
    month_end_date = today.replace(day=28) + timedelta(days=4)
    month_end = timezone.make_aware(datetime.combine(month_end_date.replace(day=1), datetime.min.time()))
    current_month = completed.filter(completed_at__gte=month_start, completed_at__lt=month_end)
    pending_count = Booking.objects.filter(service__provider__user=request.user, status=Booking.Status.PENDING).count()

    first_month = (today.replace(day=1) - timedelta(days=150)).replace(day=1)
    months = []
    cursor = first_month
    for _ in range(6):
        start = timezone.make_aware(datetime.combine(cursor, datetime.min.time()))
        next_date = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = timezone.make_aware(datetime.combine(next_date, datetime.min.time()))
        amount = completed.filter(completed_at__gte=start, completed_at__lt=end).aggregate(total=Sum("price_at_booking"))["total"] or 0
        months.append({"label": cursor.strftime("%b %Y"), "amount": amount})
        cursor = next_date
    peak = max((row["amount"] for row in months), default=0)
    for row in months:
        row["percent"] = max(3, int(row["amount"] * 100 / peak)) if peak else 3
    return render(request, "dashboard/provider_earnings.html", {
        "total_earnings": completed.aggregate(total=Sum("price_at_booking"))["total"] or 0,
        "month_earnings": current_month.aggregate(total=Sum("price_at_booking"))["total"] or 0,
        "completed_count": completed.count(),
        "pending_count": pending_count,
        "earnings_months": months,
        "history": completed.select_related("service", "customer").order_by("-completed_at", "-pk")[:50],
    })

@login_required
def service_manage(request, pk=None):
    if request.user.role != User.Role.PROVIDER or not request.user.is_active: return forbidden_response(request)
    obj = get_object_or_404(Service, pk=pk, provider__user=request.user) if pk else None
    form = ServiceForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        service = form.save(commit=False)
        if not obj: service.provider = request.user.provider_profile
        service.save(); messages.success(request, "Service saved."); return redirect("dashboard")
    return render(request, "form_page.html", {"form": form, "title": "Edit service" if obj else "Add a service"})
