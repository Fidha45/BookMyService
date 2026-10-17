from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ProviderProfile, WeeklyAvailability, AvailabilityBlock

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    fieldsets = ((None, {"fields": ("email", "password")}), ("Personal info", {"fields": ("first_name", "last_name", "phone", "role")}), ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}), ("Important dates", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")} ),)
    search_fields = ("email", "first_name", "last_name")
    filter_horizontal = ("groups", "user_permissions")
@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "location", "experience_years", "approval_status", "is_verified")
    list_filter = ("approval_status", "is_verified")
    search_fields = ("display_name", "user__email", "location")
    readonly_fields = ("approval_status", "approval_reviewed_at", "is_verified")
admin.site.register(WeeklyAvailability)
admin.site.register(AvailabilityBlock)
