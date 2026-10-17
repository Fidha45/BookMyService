from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from accounts.models import ProviderProfile, User, WeeklyAvailability
from services.models import Category, Service
from bookings.logic import create_booking, transition
from bookings.models import Booking
from .models import Review

class ReviewRulesTests(TestCase):
    def test_nonexistent_booking_is_reported_as_validation_error(self):
        review = Review(booking_id=999999, customer_id=999999, rating=5)
        with self.assertRaises(ValidationError):
            review.full_clean()

    def test_review_must_follow_completion_and_is_unique(self):
        provider_user = User.objects.create_user(email="provider@example.test", password="Strong-pass-123", role="provider")
        profile = ProviderProfile.objects.create(user=provider_user, display_name="Pro", location="Pune")
        customer = User.objects.create_user(email="customer@example.test", password="Strong-pass-123", role="customer")
        category = Category.objects.create(name="Cleaning", slug="cleaning")
        service = Service.objects.create(provider=profile, category=category, name="Clean", description="", location="Pune", price=300, duration_minutes=30)
        day = timezone.localdate() + timedelta(days=8)
        WeeklyAvailability.objects.create(provider=profile, weekday=day.weekday(), start_time="09:00", end_time="17:00")
        start = timezone.make_aware(datetime.combine(day, datetime.strptime("11:00", "%H:%M").time()))
        booking = create_booking(customer, service, start)
        review = Review(booking=booking, customer=customer, rating=5, text="Premature")
        with self.assertRaises(ValidationError): review.full_clean()
        transition(booking, Booking.Status.CONFIRMED, provider_user)
        transition(booking, Booking.Status.IN_PROGRESS, provider_user)
        transition(booking, Booking.Status.COMPLETED, provider_user)
        Review.objects.create(booking=booking, customer=customer, rating=5, text="Great")
        duplicate = Review(booking=booking, customer=customer, rating=5, text="Duplicate")
        with self.assertRaises(ValidationError): duplicate.full_clean()
