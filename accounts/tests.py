from django.test import TestCase
from django.urls import reverse
from .models import ProviderProfile, User

class AccountTests(TestCase):
    def test_registration_creates_customer_and_rejects_admin_role(self):
        response = self.client.post(reverse("register"), {"first_name":"A Customer", "email":"person@example.test", "phone":"+91 1234567890", "role":"customer", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="person@example.test")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password("Test-Strong-Pass-123!"))
        self.assertNotEqual(user.password, "Test-Strong-Pass-123!")
        rejected = self.client.post(reverse("register"), {"first_name":"Attacker", "email":"attacker@example.test", "phone":"1234567890", "role":"admin", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(User.objects.filter(email="attacker@example.test").exists())

    def test_duplicate_email_and_invalid_login(self):
        User.objects.create_user(email="person@example.test", password="Test-Strong-Pass-123!")
        response = self.client.post(reverse("register"), {"first_name":"Again", "email":"person@example.test", "phone":"1234567890", "role":"customer", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="person@example.test").count(), 1)
        self.assertFalse(self.client.login(email="person@example.test", password="wrong"))

    def test_login_logout_and_deactivated_session(self):
        user = User.objects.create_user(email="login@example.test", password="Test-Strong-Pass-123!")
        self.assertTrue(self.client.login(email="login@example.test", password="Test-Strong-Pass-123!"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.force_login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_successful_account_login_redirects_each_role_to_its_dashboard(self):
        password = "Test-Strong-Pass-123!"
        customer = User.objects.create_user(email="customer-login@example.test", password=password, first_name="Casey")
        provider = User.objects.create_user(email="provider-login@example.test", password=password, role=User.Role.PROVIDER)
        ProviderProfile.objects.create(user=provider, display_name="Local Provider", location="Delhi")
        admin = User.objects.create_user(email="admin-login@example.test", password=password, role=User.Role.ADMIN, is_staff=True)

        for user in (customer, provider, admin):
            with self.subTest(role=user.role):
                from django.test import Client
                client = Client()
                response = client.post(reverse("login"), {"username": user.email, "password": password})
                expected_landing = "service_list" if user.role == User.Role.CUSTOMER else "dashboard"
                self.assertRedirects(response, reverse(expected_landing))
                landing = client.get(reverse(expected_landing))
                dashboard = client.get(reverse("dashboard"))
                self.assertEqual(dashboard.status_code, 200)
                if user.role == User.Role.CUSTOMER:
                    self.assertContains(dashboard, "Welcome back, Casey")
                    self.assertContains(landing, "showcase-hero")
                    self.assertContains(landing, "customer-sidebar")
                    self.assertContains(landing, '<body class="customer-app customer-sidebar-collapsed ')
                    self.assertContains(landing, 'aria-expanded="false" aria-label="Open navigation sidebar"')
                elif user.role == User.Role.PROVIDER:
                    self.assertContains(dashboard, "Provider dashboard")
                else:
                    self.assertContains(dashboard, "Welcome back, Admin.")

    def test_login_page_preserves_safe_return_destination(self):
        response = self.client.get(reverse("login"), {"next": "/bookings/new/1/"})
        self.assertContains(response, 'name="next" value="/bookings/new/1/"')

    def test_login_page_has_administrator_sign_in_option(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Administrator?")
        self.assertContains(response, 'href="/accounts/login/?next=/dashboard/"')

    def test_provider_can_view_selected_availability_date_and_save_weekly_hours(self):
        from .models import WeeklyAvailability

        provider = User.objects.create_user(
            email="hours-provider@example.test", password="Test-Strong-Pass-123!",
            role=User.Role.PROVIDER,
        )
        ProviderProfile.objects.create(user=provider, display_name="Hours Provider", location="Kochi")
        self.client.force_login(provider)
        availability_url = reverse("provider_settings")

        response = self.client.get(availability_url, {
            "section": "availability", "date": "2026-10-22",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "22 October 2026")

        form_data = {
            "action": "save_availability", "date": "2026-10-22",
            "day-TOTAL_FORMS": "7", "day-INITIAL_FORMS": "0",
            "day-MIN_NUM_FORMS": "0", "day-MAX_NUM_FORMS": "1000",
            "day-0-start_time": "09:00", "day-0-end_time": "17:00",
        }
        response = self.client.post(f"{availability_url}?section=availability", form_data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("date=2026-10-22", response["Location"])
        hours = WeeklyAvailability.objects.get(provider=provider.provider_profile, weekday=0)
        self.assertEqual(hours.start_time.strftime("%H:%M"), "09:00")
        self.assertEqual(hours.end_time.strftime("%H:%M"), "17:00")
        self.assertEqual(self.client.get(response["Location"]).status_code, 200)

    def test_provider_location_is_saved_and_survives_a_new_login(self):
        provider = User.objects.create_user(
            email="location-provider@example.test", password="Test-Strong-Pass-123!",
            first_name="Local", role=User.Role.PROVIDER,
        )
        profile = ProviderProfile.objects.create(user=provider, display_name="Local Provider", location="Kochi")
        self.client.force_login(provider)

        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Kochi")
        self.assertContains(dashboard, "provider-location-control")
        self.assertContains(dashboard, 'id="provider-location-input"')
        self.assertContains(dashboard, 'name="location"')
        self.assertContains(dashboard, 'class="provider-bell"')
        self.assertContains(dashboard, 'class="provider-account"')
        self.assertContains(dashboard, 'class="provider-menu-toggle"')
        self.assertNotContains(dashboard, "Search bookings, services")
        self.assertNotContains(dashboard, 'class="provider-search"')
        provider_pages = [
            self.client.get(f"{reverse('dashboard')}?provider_page={page}")
            for page in ("bookings", "services", "reviews")
        ]
        provider_pages.extend([
            self.client.get(f"{reverse('provider_settings')}?section=availability"),
            self.client.get(reverse("provider_settings")),
            self.client.get(reverse("service_new")),
        ])
        for page_response in provider_pages:
            with self.subTest(path=page_response.request["PATH_INFO"]):
                self.assertEqual(page_response.status_code, 200)
                self.assertNotContains(page_response, 'class="provider-search"')

        response = self.client.post(reverse("provider_location_update"), {
            "location": "  Palarivattom   , Kochi  ", "next": reverse("provider_settings"),
        })
        self.assertRedirects(response, reverse("provider_settings"))
        profile.refresh_from_db()
        self.assertEqual(profile.location, "Palarivattom , Kochi")

        self.client.logout()
        self.assertTrue(self.client.login(email=provider.email, password="Test-Strong-Pass-123!"))
        settings_page = self.client.get(reverse("provider_settings"))
        self.assertContains(settings_page, "Palarivattom , Kochi")
        unsafe_redirect = self.client.post(reverse("provider_location_update"), {
            "location": "Kochi", "next": "https://example.invalid/",
        })
        self.assertRedirects(unsafe_redirect, reverse("dashboard"))

    def test_provider_location_validation_and_role_authorization(self):
        provider = User.objects.create_user(
            email="location-validation@example.test", password="Test-Strong-Pass-123!",
            role=User.Role.PROVIDER,
        )
        profile = ProviderProfile.objects.create(user=provider, display_name="Provider", location="Kochi")
        self.client.force_login(provider)
        endpoint = reverse("provider_location_update")

        for value in ("", "x" * 121, "Kochi\nDistrict"):
            with self.subTest(location=value):
                response = self.client.post(endpoint, {"location": value, "next": reverse("dashboard")})
                self.assertRedirects(response, reverse("dashboard"))
                profile.refresh_from_db()
                self.assertEqual(profile.location, "Kochi")
                self.assertTrue(list(response.wsgi_request._messages))

        customer = User.objects.create_user(email="location-customer@example.test", password="Test-Strong-Pass-123!")
        self.client.force_login(customer)
        self.assertEqual(self.client.post(endpoint, {"location": "Elsewhere"}).status_code, 403)
        self.client.force_login(provider)
        self.assertEqual(self.client.get(endpoint).status_code, 403)
