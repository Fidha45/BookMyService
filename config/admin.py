from django.contrib.admin import AdminSite
from django.urls import reverse


class BookMyServiceAdminSite(AdminSite):
    """Keep Django Admin intact while presenting services as one management area."""

    enable_nav_sidebar = True

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        service_app = next((app for app in app_list if app["app_label"] == "services"), None)
        if service_app is None:
            return app_list

        # Resolve the registered admins by model rather than exposing the two
        # default model links separately in the navigation.
        from services.models import Category, Service

        service_admin = self._registry.get(Service)
        category_admin = self._registry.get(Category)
        service_perms = {
            "add": bool(service_admin and service_admin.has_add_permission(request)),
            "change": bool(service_admin and service_admin.has_change_permission(request)),
            "delete": bool(service_admin and service_admin.has_delete_permission(request)),
            "view": bool(service_admin and service_admin.has_view_permission(request)),
        }
        category_perms = {
            "add": bool(category_admin and category_admin.has_add_permission(request)),
            "change": bool(category_admin and category_admin.has_change_permission(request)),
            "delete": bool(category_admin and category_admin.has_delete_permission(request)),
            "view": bool(category_admin and category_admin.has_view_permission(request)),
        }
        permitted = any(service_perms.values()) or any(category_perms.values())
        if not permitted:
            service_app["models"] = [
                model for model in service_app["models"]
                if model["object_name"] not in {"Service", "Category"}
            ]
            if not service_app["models"]:
                app_list.remove(service_app)
            return app_list

        service_app["name"] = "Marketplace"
        management_url_name = (
            "admin:services_service_management" if any(service_perms.values())
            else "admin:services_category_management"
        )
        service_app["models"] = [{
            "name": "Service Management",
            "object_name": "ServiceManagement",
            "admin_url": reverse(management_url_name),
            "add_url": None,
            "view_only": not (service_perms["add"] or service_perms["change"] or service_perms["delete"] or category_perms["add"] or category_perms["change"] or category_perms["delete"]),
            "perms": {key: service_perms[key] or category_perms[key] for key in service_perms},
        }]
        return app_list
