from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from .views import admin_home

admin.site.site_header = "BookMyService Administration"
admin.site.site_title = "BookMyService Admin"
admin.site.index_title = "Platform management"

urlpatterns = [path("admin/", admin_home, name="admin_home"), path("admin/", admin.site.urls), path("", include("services.urls")),
               path("accounts/", include("accounts.urls")), path("bookings/", include("bookings.urls")),
               path("reviews/", include("reviews.urls"))]
handler403 = "config.views.permission_denied"
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
