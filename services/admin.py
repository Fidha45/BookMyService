from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.text import slugify

from accounts.models import ProviderProfile
from .models import Category, Service


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    change_list_template = "admin/services/category/change_list.html"
    list_display = ("category_number", "category_name", "slug", "linked_service_count", "active_service_count", "listing_status")
    list_display_links = ("category_name",)
    search_fields = ("name", "slug")
    ordering = ("name",)
    list_per_page = 10

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _linked_service_count=Count("services", distinct=True),
            _active_service_count=Count(
                "services",
                filter=Q(services__is_active=True, services__provider__user__is_active=True),
                distinct=True,
            ),
        )

    def get_list_display(self, request):
        def row_actions(obj):
            links = []
            if self.has_change_permission(request, obj):
                links.append(format_html(
                    '<a class="category-row-action action-edit" href="{}" aria-label="Edit {}">Edit</a>',
                    reverse("admin:services_category_change", args=(obj.pk,)), obj.name,
                ))
            if self.has_delete_permission(request, obj):
                links.append(format_html(
                    '<a class="category-row-action action-delete" href="{}" aria-label="Delete {}">Delete</a>',
                    reverse("admin:services_category_delete", args=(obj.pk,)), obj.name,
                ))
            return format_html_join(" ", "{}", ((link,) for link in links))

        row_actions.short_description = "Actions"
        return (*super().get_list_display(request), row_actions)

    @admin.display(description="#", ordering="id")
    def category_number(self, obj):
        return getattr(obj, "_admin_row_number", obj.pk)

    @admin.display(description="Category name", ordering="name")
    def category_name(self, obj):
        return format_html(
            '<span class="category-name-cell"><span class="category-name-icon" aria-hidden="true">{}</span><strong>{}</strong></span>',
            obj.name[:1].upper(), obj.name,
        )

    @admin.display(description="Linked services", ordering="_linked_service_count")
    def linked_service_count(self, obj):
        return obj._linked_service_count

    @admin.display(description="Active services", ordering="_active_service_count")
    def active_service_count(self, obj):
        return obj._active_service_count

    @admin.display(description="Availability", ordering="_active_service_count")
    def listing_status(self, obj):
        if obj._active_service_count:
            return format_html('<span class="category-status is-active">Available</span>')
        return format_html('<span class="category-status is-inactive">No active listings</span>')

    def changelist_view(self, request, extra_context=None):
        query = {}
        if request.GET.get("q"):
            query["category_q"] = request.GET["q"]
        if request.GET.get("p"):
            query["category_page"] = request.GET["p"]
        return redirect(reverse("admin:services_category_management") + (f"?{urlencode(query)}" if query else ""))


class ServicePriceRangeFilter(admin.FieldListFilter):
    template = "admin/services/service/price_range_filter.html"

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.title = "Price range"

    def expected_parameters(self):
        return ["price__gte", "price__lte"]

    def choices(self, changelist):
        yield {
            "min_price": self.used_parameters.get("price__gte", ""),
            "max_price": self.used_parameters.get("price__lte", ""),
        }

    def queryset(self, request, queryset):
        parsed = {}
        for parameter in self.expected_parameters():
            raw = self.used_parameters.get(parameter)
            if isinstance(raw, (list, tuple)):
                raw = raw[-1] if raw else ""
            if raw in (None, ""):
                continue
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError):
                return queryset.none()
            if not value.is_finite() or value < 0:
                return queryset.none()
            parsed[parameter] = value
        minimum = parsed.get("price__gte")
        maximum = parsed.get("price__lte")
        if minimum is not None and maximum is not None and minimum > maximum:
            return queryset.none()
        return queryset.filter(**parsed) if parsed else queryset


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    change_list_template = "admin/services/service/change_list.html"
    list_display = ("service_number", "service_summary", "provider_name", "category", "price", "status_badge")
    list_display_links = ("service_summary",)
    search_fields = ("name", "provider__display_name", "location", "category__name")
    ordering = ("-created_at", "name")
    list_per_page = 10
    show_facets = admin.ShowFacets.NEVER

    class StatusFilter(SimpleListFilter):
        title = "Status"
        parameter_name = "is_active__exact"

        def lookups(self, request, model_admin):
            return (("1", "Active"), ("0", "Inactive"))

        def queryset(self, request, queryset):
            if self.value() == "1":
                return queryset.filter(is_active=True)
            if self.value() == "0":
                return queryset.filter(is_active=False)
            return queryset

    class ProviderFilter(SimpleListFilter):
        title = "Provider"
        parameter_name = "provider__id__exact"

        def lookups(self, request, model_admin):
            return Service.objects.order_by("provider__display_name").values_list(
                "provider_id", "provider__display_name"
            ).distinct()

        def queryset(self, request, queryset):
            if self.value():
                return queryset.filter(provider_id=self.value())
            return queryset

    list_filter = (StatusFilter, ProviderFilter, ("price", ServicePriceRangeFilter), "category")

    def get_urls(self):
        custom_urls = [
            path("management/", self.admin_site.admin_view(self.management_view), name="services_service_management"),
            path("management/categories/", self.admin_site.admin_view(self.category_management_view), name="services_category_management"),
            path("management/service/<int:object_id>/toggle/", self.admin_site.admin_view(self.toggle_service_status), name="services_service_toggle"),
        ]
        return custom_urls + super().get_urls()

    def category_management_view(self, request):
        return self.management_view(request, section="categories")

    def management_view(self, request, section="services"):
        category_admin = self.admin_site._registry[Category]
        services_list_allowed = self.has_view_or_change_permission(request)
        categories_list_allowed = category_admin.has_view_or_change_permission(request)
        services_allowed = services_list_allowed or self.has_add_permission(request) or self.has_delete_permission(request)
        categories_allowed = categories_list_allowed or category_admin.has_add_permission(request) or category_admin.has_delete_permission(request)
        if not (services_allowed or categories_allowed):
            raise PermissionDenied
        if section == "services" and not services_allowed and categories_allowed:
            return redirect("admin:services_category_management")
        if section == "categories" and not categories_allowed and services_allowed:
            return redirect("admin:services_service_management")

        if section == "categories" and request.method == "POST":
            if not category_admin.has_add_permission(request):
                raise PermissionDenied
            category_name = request.POST.get("name", "").strip()
            category_slug = slugify(category_name)
            if not category_name or not category_slug:
                messages.error(request, "Enter a category name that can be used to create a URL slug.")
            elif Category.objects.filter(name__iexact=category_name).exists() or Category.objects.filter(slug=category_slug).exists():
                messages.error(request, "A category with that name already exists.")
            else:
                Category.objects.create(name=category_name, slug=category_slug)
                messages.success(request, f"{category_name} was created.")
                return redirect("admin:services_category_management")

        service_queryset = Service.objects.select_related("provider", "category", "provider__user").order_by("-created_at", "name")
        if services_list_allowed:
            service_query = request.GET.get("service_q", "").strip()
            service_status = request.GET.get("service_status", "")
            service_provider = request.GET.get("service_provider", "")
            service_category = request.GET.get("service_category", "")
            price_min = request.GET.get("service_price_min", "").strip()
            price_max = request.GET.get("service_price_max", "").strip()
            if service_query:
                service_queryset = service_queryset.filter(
                    Q(name__icontains=service_query) | Q(provider__display_name__icontains=service_query)
                    | Q(category__name__icontains=service_query) | Q(description__icontains=service_query)
                )
            if service_status in {"active", "inactive"}:
                service_queryset = service_queryset.filter(is_active=(service_status == "active"))
            if service_provider.isdigit():
                service_queryset = service_queryset.filter(provider_id=int(service_provider))
            else:
                service_provider = ""
            if service_category.isdigit():
                service_queryset = service_queryset.filter(category_id=int(service_category))
            else:
                service_category = ""
            valid_prices = True
            parsed_min = parsed_max = None
            for raw, label in ((price_min, "minimum"), (price_max, "maximum")):
                if raw:
                    try:
                        parsed = Decimal(raw)
                        if not parsed.is_finite() or parsed < 0:
                            raise InvalidOperation
                        if label == "minimum":
                            parsed_min = parsed
                        else:
                            parsed_max = parsed
                    except (InvalidOperation, ValueError):
                        valid_prices = False
            if parsed_min is not None and parsed_max is not None and parsed_min > parsed_max:
                valid_prices = False
            if not valid_prices:
                service_queryset = service_queryset.none()
            else:
                if parsed_min is not None:
                    service_queryset = service_queryset.filter(price__gte=parsed_min)
                if parsed_max is not None:
                    service_queryset = service_queryset.filter(price__lte=parsed_max)
        else:
            service_query = service_status = service_provider = service_category = price_min = price_max = ""
            service_queryset = service_queryset.none()

        category_queryset = Category.objects.annotate(
            linked_service_count=Count("services", distinct=True),
            active_service_count=Count("services", filter=Q(services__is_active=True, services__provider__user__is_active=True), distinct=True),
        ).order_by("name")
        if categories_list_allowed:
            category_query = request.GET.get("category_q", "").strip()
            category_availability = request.GET.get("category_availability", "")
            if category_query:
                category_queryset = category_queryset.filter(Q(name__icontains=category_query) | Q(slug__icontains=category_query))
            if category_availability == "available":
                category_queryset = category_queryset.filter(active_service_count__gt=0)
            elif category_availability == "unavailable":
                category_queryset = category_queryset.filter(active_service_count=0)
            elif category_availability not in {"", "all"}:
                category_availability = ""
        else:
            category_query = category_availability = ""
            category_queryset = category_queryset.none()

        service_page = Paginator(service_queryset, self.list_per_page).get_page(request.GET.get("service_page", 1))
        category_page = Paginator(category_queryset, category_admin.list_per_page).get_page(request.GET.get("category_page", 1))
        for offset, row in enumerate(service_page.object_list, start=service_page.start_index()):
            row.admin_row_number = offset
        for offset, row in enumerate(category_page.object_list, start=category_page.start_index()):
            row.admin_row_number = offset

        management_url = reverse("admin:services_service_management")
        category_management_url = reverse("admin:services_category_management")
        current_url = category_management_url if section == "categories" else management_url
        def page_url(key, number):
            query = request.GET.copy()
            query[key] = number
            return f"{current_url}?{query.urlencode()}"

        service_reset_query = request.GET.copy()
        for key in ("service_q", "service_status", "service_provider", "service_category", "service_price_min", "service_price_max", "service_page"):
            service_reset_query.pop(key, None)
        category_reset_query = request.GET.copy()
        for key in ("category_q", "category_availability", "category_page"):
            category_reset_query.pop(key, None)

        providers = self.model._meta.get_field("provider").remote_field.model.objects.select_related("user").order_by("display_name")
        categories = Category.objects.order_by("name")
        context = {
            **self.admin_site.each_context(request),
            "title": "Categories" if section == "categories" else "Services",
            "management_section": section,
            "opts": self.model._meta,
            "services_allowed": services_allowed,
            "categories_allowed": categories_allowed,
            "services_list_allowed": services_list_allowed,
            "categories_list_allowed": categories_list_allowed,
            "bodyclass": "app-services model-service bms-management-page",
            "service_page": service_page,
            "category_page": category_page,
            "service_previous_url": page_url("service_page", service_page.previous_page_number()) if service_page.has_previous() else "",
            "service_next_url": page_url("service_page", service_page.next_page_number()) if service_page.has_next() else "",
            "category_previous_url": page_url("category_page", category_page.previous_page_number()) if category_page.has_previous() else "",
            "category_next_url": page_url("category_page", category_page.next_page_number()) if category_page.has_next() else "",
            "service_reset_url": management_url + (f"?{service_reset_query.urlencode()}" if service_reset_query else ""),
            "category_reset_url": category_management_url + (f"?{category_reset_query.urlencode()}" if category_reset_query else ""),
            "service_query": service_query,
            "service_status": service_status,
            "service_provider": service_provider,
            "service_category": service_category,
            "service_price_min": price_min,
            "service_price_max": price_max,
            "category_query": category_query,
            "category_availability": category_availability,
            "providers": providers,
            "categories": categories,
            "service_metrics": {
                "total": Service.objects.count(), "active": Service.objects.filter(is_active=True).count(),
                "inactive": Service.objects.filter(is_active=False).count(),
                "providers": ProviderProfile.objects.filter(services__is_active=True, user__is_active=True).distinct().count(),
            },
            "category_metrics": {
                "total": Category.objects.count(),
                "available": Category.objects.annotate(_active=Count("services", filter=Q(services__is_active=True, services__provider__user__is_active=True), distinct=True)).filter(_active__gt=0).count(),
                "services": Service.objects.count(),
                "providers": ProviderProfile.objects.filter(services__category__isnull=False).distinct().count(),
            },
            "service_add_url": reverse("admin:services_service_add"),
            "category_add_url": reverse("admin:services_category_add"),
            "service_change_url_name": "admin:services_service_change",
            "service_delete_url_name": "admin:services_service_delete",
            "category_change_url_name": "admin:services_category_change",
            "category_delete_url_name": "admin:services_category_delete",
            "service_toggle_url_name": "admin:services_service_toggle",
        }
        return TemplateResponse(request, "admin/services/management.html", context)

    def toggle_service_status(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        service = get_object_or_404(Service, pk=object_id)
        if not self.has_change_permission(request, service):
            raise PermissionDenied
        service.is_active = not service.is_active
        service.save(update_fields=["is_active"])
        messages.success(request, f"{service.name} is now {'active' if service.is_active else 'inactive'}.")
        query = urlencode({key: value for key, value in request.POST.items() if key.startswith(("service_", "category_")) and key not in {"service_page", "category_page"} and value})
        return redirect(reverse("admin:services_service_management") + (f"?{query}" if query else ""))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("provider", "provider__user", "category")

    @admin.display(description="#", ordering="id")
    def service_number(self, obj):
        return getattr(obj, "_admin_row_number", obj.pk)

    @admin.display(description="Service", ordering="name")
    def service_summary(self, obj):
        if obj.image:
            image = format_html('<img class="service-admin-thumb" src="{}" alt="">', obj.image.url)
        else:
            image = format_html('<span class="service-admin-thumb service-admin-thumb-fallback" aria-hidden="true">{}</span>', obj.name[:1].upper())
        return format_html(
            '<span class="service-admin-summary">{}<span><strong>{}</strong><small>{}</small></span></span>',
            image, obj.name, obj.description[:90] or obj.location,
        )

    @admin.display(description="Provider", ordering="provider__display_name")
    def provider_name(self, obj):
        return obj.provider.display_name

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        label = "Active" if obj.is_active else "Inactive"
        style = "is-active" if obj.is_active else "is-inactive"
        return format_html('<span class="category-status {}">{}</span>', style, label)

    def get_list_display(self, request):
        def row_actions(obj):
            links = []
            if self.has_change_permission(request, obj):
                links.append(format_html(
                    '<a class="category-row-action action-edit" href="{}" aria-label="Edit {}">Edit</a>',
                    reverse("admin:services_service_change", args=(obj.pk,)), obj.name,
                ))
            if self.has_delete_permission(request, obj):
                links.append(format_html(
                    '<a class="category-row-action action-delete" href="{}" aria-label="Delete {}">Delete</a>',
                    reverse("admin:services_service_delete", args=(obj.pk,)), obj.name,
                ))
            return format_html_join(" ", "{}", ((link,) for link in links))

        row_actions.short_description = "Actions"
        return (*super().get_list_display(request), row_actions)

    def changelist_view(self, request, extra_context=None):
        query = {}
        mapping = {
            "q": "service_q", "p": "service_page", "is_active__exact": "service_status",
            "provider__id__exact": "service_provider", "category__id__exact": "service_category",
            "price__gte": "service_price_min", "price__lte": "service_price_max",
        }
        for old_key, new_key in mapping.items():
            value = request.GET.get(old_key)
            if value not in (None, ""):
                if old_key == "is_active__exact":
                    value = "active" if value == "1" else "inactive" if value == "0" else ""
                if value:
                    query[new_key] = value
        return redirect(reverse("admin:services_service_management") + (f"?{urlencode(query)}" if query else ""))

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.bookings.exists():
            readonly.append("provider")
        return readonly
