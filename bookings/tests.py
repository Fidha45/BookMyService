from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import ProviderProfile, User, WeeklyAvailability
from services.models import Category, Service
from .logic import available_slots, create_booking, transition
from .models import Booking

class BookingRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.provider_user = User.objects.create_user(email="pro@example.test", password="Strong-pass-123", role="provider")
        cls.profile = ProviderProfile.objects.create(user=cls.provider_user, display_name="Handy Pro", location="Pune")
        cls.customer = User.objects.create_user(email="customer@example.test", password="Strong-pass-123", role="customer")
        cls.other_customer = User.objects.create_user(email="other@example.test", password="Strong-pass-123", role="customer")
        cls.category = Category.objects.create(name="Home", slug="home")
        cls.service = Service.objects.create(provider=cls.profile, category=cls.category, name="Repair", description="Repairs", location="Pune", price=500, duration_minutes=60)

    def setUp(self):
        day = timezone.localdate() + timedelta(days=7)
        self.day = day + timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.update_or_create(provider=self.profile, weekday=self.day.weekday(), defaults={"start_time": "09:00", "end_time": "17:00"})
        self.start = timezone.make_aware(datetime.combine(self.day, datetime.strptime("10:00", "%H:%M").time()))

    def test_booking_creation_and_partial_overlap_rejected(self):
        first = create_booking(self.customer, self.service, self.start)
        self.assertEqual(first.end_at - first.start_at, timedelta(hours=1))
        with self.assertRaises(ValidationError):
            create_booking(self.other_customer, self.service, self.start + timedelta(minutes=30))

    def test_exact_duplicate_interval_is_rejected(self):
        create_booking(self.customer, self.service, self.start)
        with self.assertRaises(ValidationError):
            create_booking(self.other_customer, self.service, self.start)

    def test_adjacent_booking_is_allowed(self):
        create_booking(self.customer, self.service, self.start)
        adjacent = create_booking(self.other_customer, self.service, self.start + timedelta(hours=1))
        self.assertEqual(adjacent.start_at, self.start + timedelta(hours=1))

    def test_rejected_booking_releases_its_slot(self):
        booking = create_booking(self.customer, self.service, self.start)
        transition(booking, Booking.Status.REJECTED, self.provider_user)
        replacement = create_booking(self.other_customer, self.service, self.start)
        self.assertEqual(replacement.start_at, self.start)

    def test_reschedule_into_occupied_slot_preserves_original_booking(self):
        from .logic import reschedule_booking
        first = create_booking(self.customer, self.service, self.start)
        occupied = create_booking(self.other_customer, self.service, self.start + timedelta(hours=2))
        with self.assertRaises(ValidationError):
            reschedule_booking(first, occupied.start_at)
        first.refresh_from_db()
        self.assertEqual(first.start_at, self.start)

    def test_successful_reschedule_releases_old_slot(self):
        from .logic import reschedule_booking
        booking = create_booking(self.customer, self.service, self.start)
        new_start = self.start + timedelta(hours=2)
        reschedule_booking(booking, new_start)
        booking.refresh_from_db()
        self.assertEqual(booking.start_at, new_start)
        replacement = create_booking(self.other_customer, self.service, self.start)
        self.assertEqual(replacement.start_at, self.start)

    def test_naive_time_and_zero_duration_are_rejected(self):
        with self.assertRaises(ValidationError):
            create_booking(self.customer, self.service, datetime.combine(self.day, datetime.strptime("10:00", "%H:%M").time()))
        Service.objects.filter(pk=self.service.pk).update(duration_minutes=0)
        invalid_service = Service.objects.get(pk=self.service.pk)
        with self.assertRaises(ValidationError):
            create_booking(self.customer, invalid_service, self.start)

    def test_booking_uses_service_duration_from_locked_database_row(self):
        stale_service = Service.objects.get(pk=self.service.pk)
        Service.objects.filter(pk=self.service.pk).update(duration_minutes=120)
        booking = create_booking(self.customer, stale_service, self.start)
        self.assertEqual(booking.duration_at_booking, 120)
        self.assertEqual(booking.end_at - booking.start_at, timedelta(hours=2))

    def test_cancelled_booking_releases_slot(self):
        booking = create_booking(self.customer, self.service, self.start)
        transition(booking, Booking.Status.CANCELLED, self.customer)
        replacement = create_booking(self.other_customer, self.service, self.start)
        self.assertEqual(replacement.start_at, self.start)

    def test_request_outside_availability_is_rejected(self):
        outside = self.start.replace(hour=18)
        with self.assertRaises(ValidationError): create_booking(self.customer, self.service, outside)

    def test_failed_reschedule_preserves_original_booking(self):
        first = create_booking(self.customer, self.service, self.start)
        occupied = create_booking(self.other_customer, self.service, self.start + timedelta(hours=2))
        with self.assertRaises(ValidationError):
            from .logic import reschedule_booking
            reschedule_booking(first, occupied.start_at + timedelta(minutes=30))
        first.refresh_from_db()
        self.assertEqual(first.start_at, self.start)

    def test_completed_booking_cannot_be_rescheduled(self):
        from .logic import reschedule_booking
        booking = create_booking(self.customer, self.service, self.start)
        transition(booking, Booking.Status.CONFIRMED, self.provider_user)
        transition(booking, Booking.Status.IN_PROGRESS, self.provider_user)
        transition(booking, Booking.Status.COMPLETED, self.provider_user)
        with self.assertRaises(ValidationError):
            reschedule_booking(booking, self.start + timedelta(hours=2))
        booking.refresh_from_db()
        self.assertEqual(booking.start_at, self.start)

    def test_past_slot_is_rejected(self):
        past = timezone.now() - timedelta(days=1)
        with self.assertRaises(ValidationError): create_booking(self.customer, self.service, past)

    def test_available_slots_respect_duration_and_existing_bookings(self):
        booking = create_booking(self.customer, self.service, self.start)
        slots = available_slots(self.service, self.day)
        self.assertNotIn(self.start, slots)
        self.assertNotIn(self.start + timedelta(minutes=30), slots)
        self.assertIn(booking.end_at, slots)

    def test_customer_cannot_set_provider_status(self):
        booking = create_booking(self.customer, self.service, self.start)
        with self.assertRaises(ValidationError):
            transition(booking, Booking.Status.CONFIRMED, self.customer)

    def test_provider_can_manage_booking_through_dashboard_actions(self):
        booking = create_booking(self.customer, self.service, self.start)
        self.client.force_login(self.provider_user)
        for action, expected_status in (
            ("confirm", Booking.Status.CONFIRMED),
            ("start", Booking.Status.IN_PROGRESS),
            ("complete", Booking.Status.COMPLETED),
        ):
            response = self.client.post(reverse("booking_action", args=[booking.pk, action]))
            self.assertEqual(response.status_code, 302)
            booking.refresh_from_db()
            self.assertEqual(booking.status, expected_status)

    def test_provider_can_cancel_own_booking_through_dashboard_action(self):
        booking = create_booking(self.customer, self.service, self.start)
        self.client.force_login(self.provider_user)
        response = self.client.post(reverse("booking_action", args=[booking.pk, "cancel"]))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_other_provider_cannot_manage_booking(self):
        booking = create_booking(self.customer, self.service, self.start)
        other_provider = User.objects.create_user(email="other-pro@example.test", password="Strong-pass-123", role="provider")
        self.client.force_login(other_provider)
        response = self.client.post(reverse("booking_action", args=[booking.pk, "confirm"]))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_own_customer_cannot_cancel_inside_two_hours(self):
        booking = create_booking(self.customer, self.service, self.start)
        booking.start_at = timezone.now() + timedelta(minutes=90)
        booking.save(update_fields=["start_at"])
        with self.assertRaises(ValidationError):
            transition(booking, Booking.Status.CANCELLED, self.customer)

    def test_customer_can_cancel_exactly_two_hours_before(self):
        from unittest.mock import patch
        booking = create_booking(self.customer, self.service, self.start)
        with patch("bookings.logic.timezone.now", return_value=self.start - timedelta(hours=2)):
            transition(booking, Booking.Status.CANCELLED, self.customer)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_customer_dashboard_shows_history_and_reschedule_controls(self):
        booking = create_booking(self.customer, self.service, self.start)
        self.client.force_login(self.customer)
        response = self.client.get(reverse("dashboard"), {"view": "bookings"})
        self.assertContains(response, "Previous")
        self.assertContains(response, reverse("booking_action", args=[booking.pk, "reschedule"]))
        self.assertContains(response, reverse("booking_action", args=[booking.pk, "cancel"]))

class RelationalBookingRaceTests(TransactionTestCase):
    """Exercise row locks on server DBs and writer serialization on file SQLite."""

    def test_concurrent_http_booking_requests_for_one_slot_have_one_winner(self):
        import threading
        from django.db import close_old_connections
        from django.test import Client
        provider = User.objects.create_user(email="http-race-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="HTTP race", location="Delhi")
        customers = [User.objects.create_user(email=f"http-race{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="HTTP race category", slug="http-race-category")
        service = Service.objects.create(provider=profile, category=category, name="HTTP race service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("10:00", "%H:%M").time()))
        clients = [Client() for _ in customers]
        for client, customer in zip(clients, customers):
            client.force_login(customer)
        barrier = threading.Barrier(2)
        outcomes = []

        def post_booking(client):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = client.post(reverse("book_service", args=[service.pk]), {"start_at": start.isoformat()})
                outcomes.append("created" if response.status_code == 302 else "conflict")
            finally:
                close_old_connections()

        threads = [threading.Thread(target=post_booking, args=(client,)) for client in clients]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Concurrent HTTP booking requests timed out.")
        self.assertCountEqual(outcomes, ["created", "conflict"])
        self.assertEqual(Booking.objects.filter(service__provider=profile, status__in=Booking.OCCUPYING).count(), 1)

    def test_two_simultaneous_overlapping_requests_have_one_winner(self):
        import threading
        from django.db import close_old_connections
        provider = User.objects.create_user(email="race-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Race", location="Delhi")
        customers = [User.objects.create_user(email=f"race{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="Race category", slug="race-category")
        service = Service.objects.create(provider=profile, category=category, name="Race service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("10:00", "%H:%M").time()))
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(customer_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                customer = User.objects.get(pk=customer_id)
                current_service = Service.objects.get(pk=service.pk)
                create_booking(customer, current_service, start)
                outcomes.append("created")
            except ValidationError:
                outcomes.append("conflict")
            finally:
                close_old_connections()
        threads = [threading.Thread(target=attempt, args=(customer.pk,)) for customer in customers]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Concurrent booking requests timed out.")
        self.assertCountEqual(outcomes, ["created", "conflict"])
        self.assertEqual(Booking.objects.filter(service__provider=profile, status__in=Booking.OCCUPYING).count(), 1)

    def test_booking_racing_with_cancellation_never_leaves_duplicate_active_slots(self):
        import threading
        from django.db import close_old_connections
        provider = User.objects.create_user(email="cancel-race-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Cancel race", location="Delhi")
        customers = [User.objects.create_user(email=f"cancel-race{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="Cancel race category", slug="cancel-race-category")
        service = Service.objects.create(provider=profile, category=category, name="Cancel race service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("10:00", "%H:%M").time()))
        existing = create_booking(customers[0], service, start)
        barrier = threading.Barrier(2)
        outcomes = []

        def cancel_existing():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                transition(Booking.objects.get(pk=existing.pk), Booking.Status.CANCELLED, User.objects.get(pk=customers[0].pk))
                outcomes.append("cancelled")
            finally:
                close_old_connections()

        def book_released_slot():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_booking(User.objects.get(pk=customers[1].pk), Service.objects.get(pk=service.pk), start)
                outcomes.append("created")
            except ValidationError:
                outcomes.append("conflict")
            finally:
                close_old_connections()

        threads = [threading.Thread(target=cancel_existing), threading.Thread(target=book_released_slot)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Concurrent cancellation and booking timed out.")
        self.assertEqual(len(outcomes), 2)
        self.assertIn("cancelled", outcomes)
        booking_result = next(result for result in outcomes if result != "cancelled")
        self.assertIn(booking_result, {"created", "conflict"})
        active = Booking.objects.filter(service__provider=profile, start_at=start, status__in=Booking.OCCUPYING)
        self.assertLessEqual(active.count(), 1)
        if booking_result == "created":
            self.assertEqual(active.count(), 1)
        else:
            self.assertEqual(active.count(), 0)

    def test_two_simultaneous_requests_for_different_slots_both_succeed(self):
        import threading
        from django.db import close_old_connections
        provider = User.objects.create_user(email="different-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Different", location="Delhi")
        customers = [User.objects.create_user(email=f"different{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="Different category", slug="different-category")
        service = Service.objects.create(provider=profile, category=category, name="Different service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        starts = [timezone.make_aware(datetime.combine(day, datetime.strptime(hour, "%H:%M").time())) for hour in ("10:00", "12:00")]
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(customer_id, start):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                create_booking(User.objects.get(pk=customer_id), Service.objects.get(pk=service.pk), start)
                outcomes.append("created")
            except ValidationError:
                outcomes.append("conflict")
            finally:
                close_old_connections()
        threads = [threading.Thread(target=attempt, args=(customer.pk, start)) for customer, start in zip(customers, starts)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Concurrent requests timed out.")
        self.assertCountEqual(outcomes, ["created", "created"])
        self.assertEqual(Booking.objects.filter(service__provider=profile, status__in=Booking.OCCUPYING).count(), 2)

    def test_two_simultaneous_reschedules_into_same_slot_have_one_winner(self):
        import threading
        from django.db import close_old_connections
        from .logic import reschedule_booking
        provider = User.objects.create_user(email="reschedule-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Reschedule", location="Delhi")
        customers = [User.objects.create_user(email=f"reschedule{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="Reschedule category", slug="reschedule-category")
        service = Service.objects.create(provider=profile, category=category, name="Reschedule service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        starts = [timezone.make_aware(datetime.combine(day, datetime.strptime(hour, "%H:%M").time())) for hour in ("10:00", "12:00")]
        target = timezone.make_aware(datetime.combine(day, datetime.strptime("14:00", "%H:%M").time()))
        bookings = [create_booking(customer, service, start) for customer, start in zip(customers, starts)]
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(booking_id):
            close_old_connections()
            try:
                booking = Booking.objects.get(pk=booking_id)
                barrier.wait(timeout=10)
                reschedule_booking(booking, target)
                outcomes.append("rescheduled")
            except ValidationError:
                outcomes.append("conflict")
            finally:
                close_old_connections()
        threads = [threading.Thread(target=attempt, args=(booking.pk,)) for booking in bookings]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=30)
        self.assertTrue(all(not thread.is_alive() for thread in threads), "Concurrent reschedules timed out.")
        self.assertCountEqual(outcomes, ["rescheduled", "conflict"])
        self.assertEqual(Booking.objects.filter(service__provider=profile, start_at=target, status__in=Booking.OCCUPYING).count(), 1)

    def test_database_guard_rejects_direct_overlapping_insert(self):
        from django.db import DatabaseError, connection, transaction
        if connection.vendor not in {"postgresql", "mysql"}:
            self.skipTest("SQLite protects application writes with provider serialization; SQL interval constraints require MySQL or PostgreSQL.")
        provider = User.objects.create_user(email="constraint-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Constraint", location="Delhi")
        customers = [User.objects.create_user(email=f"constraint{i}@example.test", password="Strong-pass-123", role="customer") for i in range(2)]
        category = Category.objects.create(name="Constraint category", slug="constraint-category")
        service = Service.objects.create(provider=profile, category=category, name="Constraint service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("10:00", "%H:%M").time()))
        create_booking(customers[0], service, start)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                Booking.objects.create(
                    customer=customers[1], service=service, provider_lock=profile,
                    start_at=start, end_at=start + timedelta(hours=1),
                    price_at_booking=service.price, duration_at_booking=60,
                    status=Booking.Status.PENDING,
                )

class BookingPageTests(TestCase):
    def test_customer_sees_and_can_request_a_generated_slot(self):
        provider = User.objects.create_user(email="page-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Page Pro", location="Delhi")
        customer = User.objects.create_user(email="page-customer@example.test", password="Strong-pass-123", role="customer")
        category = Category.objects.create(name="Page category", slug="page-category")
        service = Service.objects.create(provider=profile, category=category, name="Page service", description="", location="Delhi", price=100, duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="12:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("09:00", "%H:%M").time()))
        self.client.force_login(customer)
        page = self.client.get(reverse("book_service", args=[service.pk]), {"date": day.isoformat(), "start_at": start.strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'value="{start.strftime("%Y-%m-%dT%H:%M")}"')
        self.assertContains(page, f'value="{start.strftime("%Y-%m-%dT%H:%M")}" checked')
        response = self.client.post(reverse("book_service", args=[service.pk]), {"date": day.isoformat(), "start_at": start.strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Booking.objects.filter(customer=customer, service=service).count(), 1)

    def test_provider_cannot_submit_customer_booking(self):
        provider = User.objects.create_user(email="role-provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider, display_name="Role Pro", location="Delhi")
        category = Category.objects.create(name="Role category", slug="role-category")
        service = Service.objects.create(provider=profile, category=category, name="Role service", description="", location="Delhi", price=100, duration_minutes=60)
        self.client.force_login(provider)
        response = self.client.post(reverse("book_service", args=[service.pk]), {"start_at": "2030-01-01T10:00"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.filter(service=service).count(), 0)


class ExtendedFeatureTests(TestCase):
    def setUp(self):
        from accounts.models import ProviderProfile, User, WeeklyAvailability
        from services.models import Category, Service
        self.provider = User.objects.create_user(email="extra-provider@example.test", password="Strong-pass-123", role="provider")
        self.profile = ProviderProfile.objects.create(user=self.provider, display_name="Extra Pro", location="Pune")
        self.customer = User.objects.create_user(email="extra-customer@example.test", password="Strong-pass-123", role="customer")
        self.other = User.objects.create_user(email="extra-other@example.test", password="Strong-pass-123", role="customer")
        self.category = Category.objects.create(name="Extra", slug="extra")
        self.service = Service.objects.create(provider=self.profile, category=self.category, name="Extra service", description="", location="Pune", price="123.50", duration_minutes=60)
        day = timezone.localdate() + timedelta(days=7)
        day += timedelta(days=(0 - day.weekday()) % 7)
        WeeklyAvailability.objects.create(provider=self.profile, weekday=day.weekday(), start_time="09:00", end_time="15:00")
        self.start = timezone.make_aware(datetime.combine(day, datetime.strptime("10:00", "%H:%M").time()))
        self.booking = create_booking(self.customer, self.service, self.start)

    def test_successful_payment_confirmation_is_private_and_shows_booking_data(self):
        from django.urls import reverse
        from .models import Payment
        payment = Payment.objects.create(
            booking=self.booking,
            amount=self.booking.price_at_booking,
            status=Payment.Status.SUCCEEDED,
            verified_at=timezone.now(),
        )
        self.client.force_login(self.customer)
        response = self.client.get(reverse("payment_confirmation", args=[payment.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment confirmed!")
        self.assertContains(response, "Extra service")
        self.assertContains(response, "Extra Pro")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("payment_confirmation", args=[payment.pk])).status_code, 404)

    def test_only_one_active_payment_is_allowed_but_failed_attempt_history_is_kept(self):
        from django.db import IntegrityError, transaction
        from .models import Payment

        Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking, status=Payment.Status.FAILED)
        Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking, status=Payment.Status.FAILED)
        active = Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking)
        active.refresh_from_db()
        self.assertEqual(active.active_booking_id, self.booking.pk)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking)
        active.status = Payment.Status.FAILED
        active.save(update_fields=["status", "updated_at"])
        retry = Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking)
        retry.refresh_from_db()
        self.assertEqual(retry.active_booking_id, self.booking.pk)

    def test_favourite_unique_constraints_use_nullable_target_columns(self):
        from django.db import IntegrityError, transaction
        from services.models import Favourite

        Favourite.objects.create(customer=self.customer, service=self.service)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favourite.objects.create(customer=self.customer, service=self.service)
        other_service = Service.objects.create(
            provider=self.profile,
            category=self.category,
            name="Second favourite service",
            description="",
            location="Pune",
            price=50,
            duration_minutes=30,
        )
        Favourite.objects.create(customer=self.customer, service=other_service)

        Favourite.objects.create(customer=self.customer, provider=self.profile)
        other_provider_user = User.objects.create_user(email="favourite-provider@example.test", password="Strong-pass-123", role="provider")
        other_provider = ProviderProfile.objects.create(user=other_provider_user, display_name="Other provider", location="Delhi")
        Favourite.objects.create(customer=self.customer, service=None, provider=other_provider)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favourite.objects.create(customer=self.customer, provider=self.profile)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Favourite.objects.create(customer=self.customer, service=None, provider=None)

    def test_payment_checkout_uses_selected_booking_and_offers_gateway_methods(self):
        from django.test import override_settings
        from django.urls import reverse
        from .models import Payment
        payment = Payment.objects.create(
            booking=self.booking,
            amount=self.booking.price_at_booking,
            gateway_order_id="order_test_checkout",
        )
        self.client.force_login(self.customer)
        with override_settings(RAZORPAY_KEY_ID="rzp_test_public", RAZORPAY_KEY_SECRET="test_secret"):
            response = self.client.post(reverse("pay_booking", args=[self.booking.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment &amp; Booking")
        self.assertContains(response, "UPI")
        self.assertContains(response, "Debit / Credit card")
        self.assertContains(response, payment.gateway_order_id)
        self.assertContains(response, "GPay")

    def test_checkout_preview_stays_visible_when_gateway_is_not_configured(self):
        from django.test import override_settings
        from django.urls import reverse
        from .models import Payment
        self.client.force_login(self.customer)
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
            response = self.client.post(reverse("pay_booking", args=[self.booking.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Online payment is unavailable")
        self.assertContains(response, "No payment has been collected")
        self.assertNotContains(response, "GPay")
        self.assertFalse(response.context["gateway_ready"])
        self.assertEqual(Payment.objects.get(booking=self.booking).status, Payment.Status.CREATED)

    def test_booking_reference_and_notification_are_persisted(self):
        from .models import Notification
        self.assertTrue(self.booking.reference)
        self.assertTrue(Notification.objects.filter(recipient=self.customer, booking=self.booking).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.provider, booking=self.booking).exists())

    def test_request_key_is_idempotent(self):
        import uuid
        key = uuid.uuid4()
        first = create_booking(self.customer, self.service, self.start + timedelta(hours=2), request_key=key)
        second = create_booking(self.customer, self.service, self.start + timedelta(hours=2), request_key=key)
        self.assertEqual(first.pk, second.pk)

    def test_favourites_are_customer_scoped_and_deduplicated(self):
        from services.models import Favourite
        from django.urls import reverse
        self.client.force_login(self.customer)
        response = self.client.post(reverse("favourite_toggle", args=["service", self.service.pk]))
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse("favourite_toggle", args=["service", self.service.pk]))
        self.assertFalse(Favourite.objects.filter(customer=self.customer, service=self.service).exists())
        Favourite.objects.create(customer=self.other, service=self.service)
        self.assertEqual(self.client.get(reverse("favourites")).status_code, 200)

    def test_invoice_is_pdf_and_forbidden_to_unrelated_customer(self):
        from django.urls import reverse
        self.client.force_login(self.customer)
        response = self.client.get(reverse("booking_invoice", args=[self.booking.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.client.force_login(self.other)
        denied = self.client.get(reverse("booking_invoice", args=[self.booking.pk]))
        self.assertEqual(denied.status_code, 403)

    def test_booking_emails_are_sent_after_commit_once_per_recipient(self):
        from django.core import mail
        mail.outbox.clear()
        self.customer.email = "customer@example.test"
        self.customer.save(update_fields=["email"])
        self.provider.email = "provider@example.test"
        self.provider.save(update_fields=["email"])
        with self.captureOnCommitCallbacks(execute=True):
            from .logic import create_booking
            booking = create_booking(self.customer, self.service, self.start + timedelta(hours=2))
        self.assertEqual(len(mail.outbox), 2)
        self.assertCountEqual([email.to[0] for email in mail.outbox], [self.customer.email, self.provider.email])
        self.assertTrue(all(str(booking.reference) in email.body for email in mail.outbox))

    def test_email_failure_does_not_rollback_booking(self):
        from unittest.mock import patch
        from django.core import mail
        mail.outbox.clear()
        with patch("bookings.email_notifications.EmailMultiAlternatives.send", side_effect=OSError("mail unavailable")):
            with self.captureOnCommitCallbacks(execute=True):
                from .logic import create_booking
                booking = create_booking(self.customer, self.service, self.start + timedelta(hours=2))
        self.assertTrue(Booking.objects.filter(pk=booking.pk).exists())

    def test_completed_booking_email_is_sent_to_customer(self):
        from django.core import mail
        from .logic import transition
        Booking.objects.filter(pk=self.booking.pk).update(status=Booking.Status.CONFIRMED)
        self.booking.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            transition(self.booking, Booking.Status.IN_PROGRESS, self.provider)
            self.booking.refresh_from_db()
            transition(self.booking, Booking.Status.COMPLETED, self.provider)
        self.assertTrue(any("Service completed" in email.subject for email in mail.outbox))

    def test_booking_confirmation_filename_is_descriptive(self):
        from django.urls import reverse
        self.client.force_login(self.customer)
        response = self.client.get(reverse("booking_invoice", args=[self.booking.pk]))
        self.assertIn(f'booking-confirmation-{self.booking.pk}.pdf', response["Content-Disposition"])

    def test_payment_checkout_signature_and_server_amount_verification(self):
        from unittest.mock import patch
        from django.test import override_settings
        from django.core.exceptions import ValidationError
        from .models import Payment
        from .payments import verify_checkout
        import hashlib, hmac
        payment = Payment.objects.create(booking=self.booking, amount=self.booking.price_at_booking, gateway_order_id="order_test")
        payment_id = "pay_test"
        signature = hmac.new(b"testsecret", b"order_test|pay_test", hashlib.sha256).hexdigest()
        with override_settings(RAZORPAY_KEY_ID="test", RAZORPAY_KEY_SECRET="testsecret"):
            with patch("bookings.payments._api", return_value={"id": payment_id, "order_id": "order_test", "amount": 12350, "currency": "INR", "status": "captured"}):
                verify_checkout(payment, "order_test", payment_id, signature)
            payment.refresh_from_db()
            self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
            with self.assertRaises(ValidationError):
                verify_checkout(payment, "order_test", "pay_bad", "invalid-signature")
            payment.refresh_from_db()
            self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
            payment.status = Payment.Status.REFUNDED; payment.save(update_fields=["status"])
            with self.assertRaises(ValidationError):
                verify_checkout(payment, "order_test", payment_id, signature)
            payment.status = Payment.Status.PENDING; payment.save(update_fields=["status"])
            with patch("bookings.payments._api", return_value={"order_id": "order_test", "amount": 999, "currency": "INR", "status": "captured"}):
                with self.assertRaises(ValidationError): verify_checkout(payment, "order_test", "pay_bad", hmac.new(b"testsecret", b"order_test|pay_bad", hashlib.sha256).hexdigest())

    def test_provider_blocked_period_is_not_offered_or_bookable(self):
        from accounts.models import AvailabilityBlock
        from .logic import available_slots, transition
        AvailabilityBlock.objects.create(provider=self.profile, start_at=self.start, end_at=self.start + timedelta(hours=1), reason="Day off")
        transition(self.booking, Booking.Status.CANCELLED, self.customer)
        self.assertNotIn(self.start, available_slots(self.service, self.start.date()))
        with self.assertRaises(ValidationError): create_booking(self.other, self.service, self.start)

    def test_signed_webhook_confirms_only_matching_captured_payment(self):
        from django.test import override_settings
        from .models import Payment
        import hashlib, hmac, json
        payment = Payment.objects.create(booking=self.booking, amount="123.50", gateway_order_id="order_webhook")
        payload = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_webhook", "order_id": "order_webhook", "amount": 12350, "currency": "INR", "status": "captured"}}}}).encode()
        signature = hmac.new(b"webhook-secret", payload, hashlib.sha256).hexdigest()
        with override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret"):
            response = self.client.post("/bookings/payments/razorpay/webhook/", data=payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
            bad = self.client.post("/bookings/payments/razorpay/webhook/", data=payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="bad")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(bad.status_code, 400)
