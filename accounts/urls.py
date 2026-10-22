from django.contrib.auth import views as auth_views
from django.urls import path
from . import views
urlpatterns = [path("register/", views.register, name="register"), path("login/", views.RoleBasedLoginView.as_view(template_name="form_page.html", extra_context={"title":"Sign in"}), name="login"), path("logout/", auth_views.LogoutView.as_view(), name="logout"), path("profile/", views.profile, name="profile"), path("provider/settings/", views.provider_settings, name="provider_settings"), path("provider/location/", views.provider_location_update, name="provider_location_update"), path("provider/settings/blocks/<int:pk>/remove/", views.remove_availability_block, name="availability_block_remove")]
