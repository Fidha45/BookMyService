from django.contrib.admin.apps import AdminConfig


class BookMyServiceAdminConfig(AdminConfig):
    """Use the project's AdminSite subclass without changing model registration."""

    default_site = "config.admin.BookMyServiceAdminSite"
