from django.test import TestCase
from django.urls import reverse
from accounts.models import ProviderProfile, User
from .models import Category, Service

class ServicePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Repairs", slug="repairs")
        cls.provider = User.objects.create_user(email="provider@test.example", password="Safe-pass-123", role="provider")
        cls.provider_profile = ProviderProfile.objects.create(user=cls.provider, display_name="Provider", location="Delhi")
        cls.other = User.objects.create_user(email="other@test.example", password="Safe-pass-123", role="provider")
        cls.other_profile = ProviderProfile.objects.create(user=cls.other, display_name="Other", location="Delhi")
        cls.customer = User.objects.create_user(email="customer@test.example", password="Safe-pass-123", role="customer")
        cls.service = Service.objects.create(provider=cls.provider_profile, category=cls.category, name="Repair", description="", location="Delhi", price=100, duration_minutes=30)

    def test_customer_cannot_open_provider_service_management(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("service_new"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "THIS AREA IS RESTRICTED", status_code=403)

    def test_provider_cannot_edit_another_providers_service(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("service_edit", args=[self.service.pk]))
        self.assertEqual(response.status_code, 404)

    def test_provider_can_create_and_edit_own_service(self):
        self.client.force_login(self.provider)
        response = self.client.post(reverse("service_new"), {"category": self.category.pk, "name": "Window repair", "description": "Repair windows", "location": "Delhi", "price": "250.00", "duration_minutes": "60", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        own = Service.objects.get(name="Window repair")
        self.assertEqual(own.provider, self.provider_profile)
        response = self.client.post(reverse("service_edit", args=[own.pk]), {"category": self.category.pk, "name": "Window repair plus", "description": "Updated", "location": "Delhi", "price": "300.00", "duration_minutes": "60", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.name, "Window repair plus")

    def test_customer_dashboard_shows_pay_button_for_unpaid_upcoming_booking(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookings.models import Booking
        start = timezone.now() + timedelta(days=2)
        booking = Booking.objects.create(
            customer=self.customer,
            service=self.service,
            provider_lock=self.service.provider,
            start_at=start,
            end_at=start + timedelta(minutes=self.service.duration_minutes),
            price_at_booking=self.service.price,
            duration_at_booking=self.service.duration_minutes,
        )
        self.client.force_login(self.customer)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pay securely")
        self.assertContains(response, reverse("pay_booking", args=[booking.pk]))

    def test_catalog_only_shows_active_services(self):
        self.service.is_active = False
        self.service.save(update_fields=["is_active"])
        response = self.client.get(reverse("service_list"))
        self.assertEqual(response.context["page"].paginator.count, 0)

    def test_homepage_and_service_detail_render_database_content(self):
        home = self.client.get(reverse("service_list"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Find the right professional")
        self.assertContains(home, self.service.name)
        detail = self.client.get(reverse("service_detail", args=[self.service.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, self.provider_profile.display_name)
        explore = self.client.get(reverse("service_explore"))
        self.assertEqual(explore.status_code, 200)
        self.assertEqual(explore.context["page"].paginator.count, 1)
        self.assertTrue(all(category.active_count > 0 for category in explore.context["categories"]))

    def test_service_detail_shows_complete_provider_profile_and_offerings(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookings.models import Booking
        from reviews.models import Review
        second = Service.objects.create(
            provider=self.provider_profile, category=self.category, name="Device setup",
            description="", location="Delhi", price=250, duration_minutes=45,
        )
        now = timezone.now()
        for service, rating in ((self.service, 5), (second, 3)):
            booking = Booking.objects.create(
                customer=self.customer, service=service, provider_lock=service.provider, start_at=now-timedelta(hours=2),
                end_at=now-timedelta(hours=1), price_at_booking=service.price,
                duration_at_booking=service.duration_minutes,
                status=Booking.Status.COMPLETED, completed_at=now-timedelta(hours=1),
            )
            Review.objects.create(booking=booking, customer=self.customer, rating=rating, text="Good service")

        response = self.client.get(reverse("service_detail", args=[self.service.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["provider_average_rating"], 4)
        self.assertEqual(response.context["provider_review_count"], 2)
        self.assertContains(response, "Services offered by Provider")
        self.assertContains(response, "Device setup")
        self.assertContains(response, "Provider rating")
        self.assertContains(response, "Working hours")

    def test_service_detail_lists_related_active_services(self):
        related = Service.objects.create(provider=self.other_profile, category=self.category, name="Related repair", description="", location="Pune", price=250, duration_minutes=45)
        hidden = Service.objects.create(provider=self.other_profile, category=Category.objects.create(name="Garden", slug="garden"), name="Hidden category", description="", location="Mumbai", price=250, duration_minutes=45, is_active=False)
        response = self.client.get(reverse("service_detail", args=[self.service.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn(related, response.context["related_services"])
        self.assertNotIn(hidden, response.context["related_services"])
        self.assertContains(response, "Similar services")

    def test_service_detail_uses_static_service_art_and_real_open_slots(self):
        from datetime import datetime, time, timedelta
        from django.utils import timezone
        from django.templatetags.static import static
        from accounts.models import WeeklyAvailability
        category, _ = Category.objects.get_or_create(slug="ac-service", defaults={"name": "AC Service"})
        service = Service.objects.create(provider=self.provider_profile, category=category, name="AC maintenance", description="Filter and cooling check", location="Delhi", price=1200, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=2)
        WeeklyAvailability.objects.create(provider=self.provider_profile, weekday=day.weekday(), start_time="09:00", end_time="12:00")
        selected_start = timezone.make_aware(datetime.combine(day, time(9, 0)))
        self.client.force_login(self.customer)

        response = self.client.get(reverse("service_detail", args=[service.pk]), {"date": day.isoformat(), "start_at": selected_start.strftime("%Y-%m-%dT%H:%M")})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(slot.strftime("%Y-%m-%dT%H:%M") == selected_start.strftime("%Y-%m-%dT%H:%M") for slot in response.context["selected_slots"]))
        self.assertEqual(response.context["gallery_images"][0]["url"], static("images/services/Ac repair.jpg"))
        self.assertContains(response, "Continue to Book")
        self.assertContains(response, "is-selected")
        page_html = response.content.decode()
        self.assertLess(page_html.index('id="service-gallery-image"'), page_html.index('id="booking"'))
        self.assertLess(page_html.index('id="booking"'), page_html.index('id="overview"'))

    def test_explore_catalog_filters_and_sorts_real_services(self):
        more_expensive = Service.objects.create(provider=self.other_profile, category=self.category, name="Premium repair", description="", location="Pune", price=450, duration_minutes=45)
        response = self.client.get(reverse("service_explore"), {"category": self.category.slug, "sort": "price_high", "view": "list"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 2)
        self.assertEqual(response.context["page"].object_list[0], more_expensive)
        self.assertEqual(response.context["layout"], "list")
        self.assertContains(response, "Filters")
        self.assertContains(response, "Premium repair")
        self.assertContains(response, "2 local professionals")
        self.assertNotContains(response, "0 verified professionals")

    def test_provider_settings_and_admin_dashboard_render(self):
        self.client.force_login(self.provider)
        settings_page = self.client.get(reverse("provider_settings"))
        self.assertEqual(settings_page.status_code, 200)
        provider_dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(provider_dashboard.status_code, 200)
        self.assertContains(provider_dashboard, "Provider dashboard")
        self.assertContains(provider_dashboard, "Your estimated earnings")
        self.assertContains(provider_dashboard, "Booking requests")
        self.assertContains(provider_dashboard, "Your availability")
        self.assertContains(provider_dashboard, "Recent customer reviews")
        filtered_dashboard = self.client.get(reverse("dashboard"), {"q": "Repair"})
        self.assertEqual(filtered_dashboard.status_code, 200)
        self.assertIn(self.service, filtered_dashboard.context["services"])
        self.assertContains(filtered_dashboard, "Matching bookings")
        staff = User.objects.create_superuser(email="admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Welcome back")
        self.assertContains(dashboard, "Pending approvals")
        self.assertContains(dashboard, "Recent bookings")
        self.assertContains(dashboard, 'id="admin-menu-backdrop"')
        self.assertContains(dashboard, "Close administrator menu")
        self.assertContains(dashboard, f'href="{reverse("notifications")}"')
        self.assertContains(dashboard, 'aria-label="Notifications')

    def test_admin_provider_approval_and_rejection_actions_are_authorized_and_distinct(self):
        self.service.refresh_from_db()
        self.client.force_login(self.customer)
        denied = self.client.post(reverse("admin_provider_review", args=[self.provider_profile.pk, "approve"]))
        self.assertEqual(denied.status_code, 403)

        staff = User.objects.create_superuser(email="review-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        approved = self.client.post(reverse("admin_provider_review", args=[self.provider_profile.pk, "approve"]))
        self.assertEqual(approved.status_code, 302)
        self.provider_profile.refresh_from_db()
        self.provider.refresh_from_db()
        self.service.refresh_from_db()
        self.assertEqual(self.provider_profile.approval_status, ProviderProfile.ApprovalStatus.APPROVED)
        self.assertTrue(self.provider_profile.is_verified)
        self.assertIsNotNone(self.provider_profile.approval_reviewed_at)
        self.assertTrue(self.provider.is_active)
        self.assertTrue(self.service.is_active)

        rejected = self.client.post(reverse("admin_provider_review", args=[self.other_profile.pk, "reject"]))
        self.assertEqual(rejected.status_code, 302)
        self.other_profile.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.other_profile.approval_status, ProviderProfile.ApprovalStatus.REJECTED)
        self.assertFalse(self.other_profile.is_verified)
        self.assertTrue(self.other.is_active)
        self.assertFalse(Service.objects.filter(provider=self.other_profile).exists())

    def test_admin_provider_review_requires_post_and_rejects_unknown_actions(self):
        staff = User.objects.create_superuser(email="method-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        get_response = self.client.get(reverse("admin_provider_review", args=[self.provider_profile.pk, "approve"]))
        unknown_response = self.client.post(reverse("admin_provider_review", args=[self.provider_profile.pk, "delete"]))
        self.assertEqual(get_response.status_code, 405)
        self.assertEqual(unknown_response.status_code, 403)

    def test_admin_dashboard_search_filters_pages_without_payment_summary(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookings.models import Booking, Payment

        now = timezone.now()
        completed = Booking.objects.create(
            customer=self.customer, service=self.service, provider_lock=self.service.provider, start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, minutes=30), price_at_booking="125.00",
            duration_at_booking=30, status=Booking.Status.COMPLETED, completed_at=now,
        )
        Payment.objects.create(
            booking=completed, amount="125.00", status=Payment.Status.SUCCEEDED,
            gateway_payment_id="captured-dashboard-test", verified_at=now,
        )
        for index in range(9):
            Booking.objects.create(
                customer=self.customer, service=self.service, provider_lock=self.service.provider,
                start_at=now + timedelta(days=3 + index), end_at=now + timedelta(days=3 + index, minutes=30),
                price_at_booking="100.00", duration_at_booking=30, status=Booking.Status.PENDING,
            )

        staff = User.objects.create_superuser(email="reports-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        filtered = self.client.get(reverse("dashboard"), {
            "q": "Repair", "booking_status": Booking.Status.COMPLETED,
        })
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["booking_page"].paginator.count, 1)
        self.assertEqual(len(filtered.context["service_matches"]), 1)
        for removed_label in (
            "VERIFIED GATEWAY DATA",
            "Payment summary",
            "Captured revenue",
            "Recorded refunds",
            "Payout tracking is not available",
            "Review transactions",
            "Revenue summary",
        ):
            self.assertNotContains(filtered, removed_label)

        paged = self.client.get(reverse("dashboard"), {"booking_status": "all"})
        self.assertEqual(paged.context["booking_page"].paginator.count, 10)
        self.assertEqual(paged.context["booking_page"].paginator.num_pages, 2)
        provider_users = self.client.get(reverse("dashboard"), {"user_type": User.Role.PROVIDER})
        self.assertTrue(all(user.role == User.Role.PROVIDER for user in provider_users.context["user_page"]))

    def test_admin_can_activate_and_deactivate_customer_and_provider_accounts(self):
        staff = User.objects.create_superuser(email="account-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        self.provider.is_active = False
        self.provider.save(update_fields=["is_active"])

        response = self.client.post(reverse("admin_account_status", args=[self.provider.pk, "activate"]))
        self.assertEqual(response.status_code, 302)
        self.provider.refresh_from_db()
        self.assertTrue(self.provider.is_active)

        response = self.client.post(reverse("admin_account_status", args=[self.customer.pk, "deactivate"]))
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_admin_dashboard_exposes_requested_platform_totals_and_account_actions(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookings.models import Booking
        now = timezone.now()
        Booking.objects.create(
            customer=self.customer, service=self.service, provider_lock=self.service.provider,
            start_at=now + timedelta(days=2), end_at=now + timedelta(days=2, minutes=30),
            price_at_booking="125.00", duration_at_booking=30, status=Booking.Status.COMPLETED,
            completed_at=now,
        )
        staff = User.objects.create_superuser(email="totals-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["customers"], 1)
        self.assertEqual(response.context["stats"]["providers"], 2)
        self.assertEqual(response.context["stats"]["total_services"], 1)
        self.assertEqual(response.context["stats"]["completed"], 1)
        self.assertContains(response, reverse("admin_account_status", args=[self.customer.pk, "deactivate"]))
        self.assertNotContains(response, "Open Django Admin")
        self.assertNotContains(response, f'class="admin-sub-link" href="{reverse("admin:bookings_payment_changelist")}">Transactions</a>')
        self.assertContains(response, f'class="admin-sub-link" href="{reverse("admin:reviews_review_changelist")}">All reviews</a>')

    def test_non_admin_cannot_change_account_status_and_admin_cannot_deactivate_self(self):
        staff = User.objects.create_superuser(email="safe-admin@test.example", password="Safe-pass-123")
        self.client.force_login(self.customer)
        denied = self.client.post(reverse("admin_account_status", args=[self.provider.pk, "deactivate"]))
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(staff)
        response = self.client.post(reverse("admin_account_status", args=[staff.pk, "deactivate"]))
        self.assertEqual(response.status_code, 302)
        staff.refresh_from_db()
        self.assertTrue(staff.is_active)

    def test_admin_provider_totals_exclude_profiles_for_nonprovider_roles(self):
        ProviderProfile.objects.create(user=self.customer, display_name="Old provider profile", location="Delhi")
        staff = User.objects.create_superuser(email="counts-admin@test.example", password="Safe-pass-123")
        self.client.force_login(staff)
        response = self.client.get(reverse("dashboard"))
        stats = response.context["stats"]
        self.assertEqual(stats["providers"], 2)
        self.assertEqual(stats["providers"], stats["verified_providers"] + stats["unverified_providers"])

    def test_deterministic_match_search_uses_real_service_and_location(self):
        response = self.client.get(reverse("match_services"), {"q": "Repair", "location": "Delhi", "max_price": "150"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.service.name)
        self.assertContains(response, "No reviews yet")
        empty = self.client.get(reverse("match_services"), {"max_price": "1"})
        self.assertContains(empty, "No services match these details")

    def test_provider_earnings_are_scoped_and_include_only_completed_bookings(self):
        from datetime import timedelta
        from django.utils import timezone
        from bookings.models import Booking
        now = timezone.now()
        customer = self.customer
        completed = Booking.objects.create(customer=customer, service=self.service, provider_lock=self.service.provider, start_at=now-timedelta(days=1), end_at=now-timedelta(hours=23), price_at_booking="100.00", duration_at_booking=60, status=Booking.Status.COMPLETED, completed_at=now-timedelta(hours=1))
        Booking.objects.create(customer=customer, service=self.service, provider_lock=self.service.provider, start_at=now+timedelta(days=1), end_at=now+timedelta(days=1, hours=1), price_at_booking="80.00", duration_at_booking=60, status=Booking.Status.PENDING)
        self.client.force_login(self.provider)
        response = self.client.get(reverse("provider_earnings"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_earnings"], 100)
        self.assertEqual(response.context["month_earnings"], 100)
        self.assertEqual(response.context["completed_count"], 1)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertContains(response, str(completed.reference))

    def test_non_provider_cannot_open_provider_earnings(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("provider_earnings"))
        self.assertEqual(response.status_code, 403)


class DjangoAdminInterfaceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="panel-admin@example.test", password="Safe-pass-123")

    def test_admin_login_branding_dashboard_and_post_logout(self):
        login_page = self.client.get(reverse("admin:login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(login_page, "BookMyService")
        self.assertContains(login_page, "admin.css")

        login_response = self.client.post(reverse("admin:login"), {
            "username": self.admin.email, "password": "Safe-pass-123",
        })
        self.assertEqual(login_response.status_code, 302)
        dashboard = self.client.get(reverse("admin:index"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Platform management")
        self.assertContains(dashboard, "bms-account-menu")
        self.assertContains(dashboard, "panel-admin@example.test")
        self.assertContains(dashboard, "View site")
        self.assertContains(dashboard, "Change password")
        self.assertContains(dashboard, "Log out")
        self.assertContains(dashboard, "theme-toggle")
        self.assertContains(dashboard, "admin-wordmark")
        self.assertNotContains(dashboard, "admin-brand-label")
        self.assertEqual(self.client.get(reverse("admin:password_change")).status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)
        logout = self.client.post(reverse("admin:logout"))
        self.assertEqual(logout.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_separate_service_and_category_management_crud_filters_and_permissions(self):
        self.client.force_login(self.admin)
        provider = User.objects.create_user(email="admin-provider@example.test", password="Safe-pass-123", role=User.Role.PROVIDER)
        profile = ProviderProfile.objects.create(user=provider, display_name="Admin provider", location="Delhi")
        category = Category.objects.create(name="Admin services", slug="admin-services")
        service = Service.objects.create(provider=profile, category=category, name="Repair sample", description="Repair", location="Delhi", price=100, duration_minutes=30)
        service_add_url = reverse("admin:services_service_add")
        self.assertEqual(self.client.get(service_add_url).status_code, 200)
        created_service = self.client.post(service_add_url, {
            "provider": profile.pk, "category": category.pk, "name": "Installation sample",
            "description": "Install appliances", "location": "Delhi", "price": "200.00",
            "duration_minutes": 45, "is_active": "on", "_save": "Save",
        })
        self.assertEqual(created_service.status_code, 302)
        add_url = reverse("admin:services_category_add")
        self.assertEqual(self.client.get(add_url).status_code, 200)
        response = self.client.post(add_url, {"name": "Panel Category", "slug": "panel-category", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        panel_category = Category.objects.get(slug="panel-category")
        response = self.client.post(reverse("admin:services_category_change", args=[panel_category.pk]), {
            "name": "Updated Panel Category", "slug": "panel-category", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        panel_category.refresh_from_db()
        self.assertEqual(panel_category.name, "Updated Panel Category")
        invalid = self.client.post(add_url, {"name": "Duplicate slug", "slug": "panel-category", "_save": "Save"})
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, "already exists")

        management_url = reverse("admin:services_service_management")
        results = self.client.get(management_url, {
            "service_q": "Repair", "service_status": "active",
        })
        self.assertEqual(results.status_code, 200)
        self.assertContains(results, "Services")
        self.assertContains(results, "Categories")
        self.assertContains(results, "Review, update and manage services offered by providers.")
        self.assertContains(results, "Repair sample")
        self.assertContains(results, "Admin provider")
        self.assertNotContains(results, "Linked services")
        self.assertEqual(results.context["service_page"].paginator.count, 1)
        self.assertEqual(results.context["service_metrics"]["total"], 2)
        self.assertContains(results, 'aria-label="Edit Repair sample"')
        self.assertContains(results, 'aria-label="Delete Repair sample"')
        category_management_url = reverse("admin:services_category_management")
        categories_page = self.client.get(category_management_url, {"category_q": "admin-services"})
        self.assertEqual(categories_page.status_code, 200)
        self.assertContains(categories_page, "Admin services")
        self.assertNotContains(categories_page, "Repair sample")
        self.assertEqual(categories_page.context["category_page"].paginator.count, 1)
        self.assertEqual(categories_page.context["category_metrics"]["services"], 2)
        self.assertEqual(categories_page.context["category_page"].object_list[0].linked_service_count, 2)
        self.assertEqual(self.client.get(management_url, {"service_provider": str(profile.pk)}).context["service_page"].paginator.count, 2)
        self.assertEqual(self.client.get(management_url, {"service_price_min": "100", "service_price_max": "100"}).context["service_page"].paginator.count, 1)
        self.assertEqual(self.client.get(management_url, {"service_price_min": "-1"}).context["service_page"].paginator.count, 0)

        old_services_list = self.client.get(reverse("admin:services_service_changelist"))
        self.assertEqual(old_services_list.status_code, 302)
        self.assertEqual(old_services_list.url, management_url)
        old_categories_list = self.client.get(reverse("admin:services_category_changelist"))
        self.assertEqual(old_categories_list.status_code, 302)
        self.assertEqual(old_categories_list.url, category_management_url)

        toggle_url = reverse("admin:services_service_toggle", args=[service.pk])
        self.assertEqual(self.client.get(toggle_url).status_code, 405)
        self.assertEqual(self.client.post(toggle_url, {"service_q": "Repair", "category_q": "admin-services"}).status_code, 302)
        service.refresh_from_db()
        self.assertFalse(service.is_active)
        self.assertEqual(self.client.get(management_url, {"service_status": "inactive"}).context["service_page"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("admin:services_service_change", args=[service.pk])).status_code, 200)

        Category.objects.bulk_create([Category(name=f"Management {index}", slug=f"management-{index}") for index in range(12)])
        page_one = self.client.get(category_management_url, {"category_q": "management-"})
        self.assertEqual(page_one.context["category_page"].paginator.num_pages, 2)
        self.assertIn("category_q=management-", page_one.context["category_next_url"])
        page_two = self.client.get(page_one.context["category_next_url"])
        self.assertEqual(page_two.context["category_page"].number, 2)

        protected_delete_url = reverse("admin:services_category_delete", args=[category.pk])
        self.assertEqual(self.client.get(protected_delete_url).status_code, 200)
        self.client.post(protected_delete_url, {"post": "yes"})
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())
        deletable = Category.objects.create(name="Delete confirmation", slug="delete-confirmation")
        delete_url = reverse("admin:services_category_delete", args=[deletable.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(Category.objects.filter(pk=deletable.pk).exists())

        customer = User.objects.create_user(email="not-admin@example.test", password="Safe-pass-123", role=User.Role.CUSTOMER)
        self.client.force_login(customer)
        self.assertEqual(self.client.get(management_url).status_code, 302)
        restricted_staff = User.objects.create_user(
            email="restricted-admin@example.test", password="Safe-pass-123", role=User.Role.ADMIN, is_staff=True,
        )
        self.client.force_login(restricted_staff)
        self.assertEqual(self.client.get(management_url).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:services_service_toggle", args=[service.pk])).status_code, 403)

    def test_service_management_pages_are_separate_and_sidebar_is_removed(self):
        self.client.force_login(self.admin)
        dashboard = self.client.get(reverse("admin:index"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Service Management")
        self.assertContains(dashboard, reverse("admin:services_service_management"))
        self.assertNotContains(dashboard, 'href="/admin/services/service/"')
        self.assertNotContains(dashboard, 'href="/admin/services/category/"')
        page = self.client.get(reverse("admin:services_service_management"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="nav-sidebar"')
        self.assertNotContains(page, 'id="toggle-nav-sidebar"')
        self.assertContains(page, "Services")
        self.assertContains(page, "Categories")
        self.assertNotContains(page, "Category descriptions are not stored in the current data model")
        self.assertContains(page, 'href="%s"' % reverse("admin:services_category_management"))
        categories = self.client.get(reverse("admin:services_category_management"))
        self.assertEqual(categories.status_code, 200)
        self.assertNotContains(categories, "Repair sample")
        self.assertContains(categories, 'href="%s"' % reverse("admin:services_service_management"))
        self.assertContains(categories, "Category descriptions are not stored in the current data model")
        self.assertNotContains(page, "Availability blocks")
        self.assertNotContains(page, "Authentication and Authorization")
