from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from .models import User, ProviderProfile, WeeklyAvailability, AvailabilityBlock

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    change_list_template = "admin/accounts/user/change_list.html"
    ordering = ("email",)
    list_per_page = 8
    list_display = ("email", "first_name", "role", "date_joined", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = ((None, {"fields": ("email", "password")}), ("Personal info", {"fields": ("first_name", "last_name", "phone", "role")}), ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}), ("Important dates", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")} ),)
    search_fields = ("email", "first_name", "last_name")
    filter_horizontal = ("groups", "user_permissions")

    def changelist_view(self, request, extra_context=None):
        context = {
            "user_metrics": {
                "total": User.objects.count(),
                "customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
                "providers": User.objects.filter(role=User.Role.PROVIDER).count(),
                "joined_this_month": User.objects.filter(date_joined__year=timezone.localdate().year, date_joined__month=timezone.localdate().month).count(),
            }
        }
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            previous = User.objects.get(pk=obj.pk)
            if previous.is_active and not obj.is_active:
                if previous.pk == request.user.pk:
                    obj.is_active = True
                    self.message_user(request, "You cannot deactivate your own administrator account.", level=messages.ERROR)
                elif previous.is_superuser and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=obj.pk).exists():
                    obj.is_active = True
                    self.message_user(request, "The last active superuser account cannot be deactivated.", level=messages.ERROR)
        super().save_model(request, obj, form, change)
@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    change_list_template = "admin/accounts/providerprofile/change_list.html"
    list_display = ("display_name", "user", "service_count", "location", "joined", "approval_status", "is_verified")
    list_filter = ("approval_status", "is_verified")
    search_fields = ("display_name", "user__email", "location")
    readonly_fields = ("approval_status", "approval_reviewed_at", "is_verified")
    list_per_page = 8

    def get_urls(self):
        custom_urls = [path("approvals/", self.admin_site.admin_view(self.approval_list_view), name="accounts_providerprofile_approval_list")]
        return custom_urls + super().get_urls()

    def approval_list_view(self, request):
        if not self.has_view_or_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        query = request.GET.get("q", "").strip()
        providers = ProviderProfile.objects.select_related("user").annotate(
            approval_service_count=Count("services", distinct=True),
        ).filter(approval_status=ProviderProfile.ApprovalStatus.PENDING).order_by("user__date_joined")
        if query:
            providers = providers.filter(Q(display_name__icontains=query) | Q(user__email__icontains=query) | Q(location__icontains=query) | Q(services__name__icontains=query)).distinct()
        page = Paginator(providers, 8).get_page(request.GET.get("page", 1))
        selected = page.object_list[0] if page.object_list else None
        today = timezone.localdate()
        month_start = today.replace(day=1)
        context = {
            **self.admin_site.each_context(request),
            "title": "Pending Approvals",
            "opts": self.model._meta,
            "approval_page": page,
            "approval_query": query,
            "selected_provider": selected,
            "approval_metrics": {
                "pending": ProviderProfile.objects.filter(approval_status=ProviderProfile.ApprovalStatus.PENDING).count(),
                "approved_month": ProviderProfile.objects.filter(approval_status=ProviderProfile.ApprovalStatus.APPROVED, approval_reviewed_at__date__gte=month_start).count(),
                "rejected_month": ProviderProfile.objects.filter(approval_status=ProviderProfile.ApprovalStatus.REJECTED, approval_reviewed_at__date__gte=month_start).count(),
                "services": ProviderProfile.objects.filter(approval_status=ProviderProfile.ApprovalStatus.PENDING).aggregate(total=Count("services"))["total"],
            },
            "bodyclass": "app-accounts model-providerprofile bms-approval-page",
        }
        context["approval_previous_url"] = f"?q={query}&page={page.previous_page_number()}" if page.has_previous() else ""
        context["approval_next_url"] = f"?q={query}&page={page.next_page_number()}" if page.has_next() else ""
        return TemplateResponse(request, "admin/accounts/providerprofile/approvals.html", context)

    def changelist_view(self, request, extra_context=None):
        context = {
            "provider_metrics": {
                "total": ProviderProfile.objects.count(),
                "verified": ProviderProfile.objects.filter(is_verified=True, user__is_active=True).count(),
                "pending": ProviderProfile.objects.filter(approval_status=ProviderProfile.ApprovalStatus.PENDING).count(),
                "inactive": ProviderProfile.objects.filter(user__is_active=False).count(),
            }
        }
        context.update(extra_context or {})
        return super().changelist_view(request, extra_context=context)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user").annotate(_listed_services=Count("services"))

    @admin.display(description="Services")
    def service_count(self, obj):
        return obj._listed_services

    @admin.display(description="Joined", ordering="user__date_joined")
    def joined(self, obj):
        return obj.user.date_joined
admin.site.register(WeeklyAvailability)
admin.site.register(AvailabilityBlock)
