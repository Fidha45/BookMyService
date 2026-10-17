from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from accounts.models import ProviderProfile, User, WeeklyAvailability
from services.models import Category, Service


PROVIDERS = [
    {
        "key": "abc-tech",
        "name": "ABC Tech Services",
        "location": "Kochi",
        "experience_years": 8,
        "services": [
            ("Laptop Repair", "Laptop diagnostics, hardware repair and software troubleshooting.", "Laptop & Computer Repair", "800.00", 60),
        ],
    },
    {
        "key": "cool-care",
        "name": "CoolCare Home Services",
        "location": "Kochi",
        "experience_years": 6,
        "services": [
            ("AC Service", "AC inspection, filter cleaning and routine performance service.", "AC Service", "1500.00", 90),
            ("Appliance Repair", "Diagnosis and repair for common household appliances.", "Appliance Repair", "650.00", 60),
        ],
    },
    {
        "key": "home-essentials",
        "name": "Home Essentials",
        "location": "Kochi",
        "experience_years": 5,
        "services": [
            ("Home Cleaning", "A thorough scheduled cleaning for kitchens, living rooms and bedrooms.", "Home Cleaning", "900.00", 120),
            ("Plumbing Visit", "Inspection and repair for common tap, drain and pipe issues.", "Plumbing", "600.00", 60),
            ("Electrical Service", "Safe inspection and repair of common household electrical issues.", "Electrical", "500.00", 60),
        ],
    },
    {
        "key": "city-auto",
        "name": "City Auto Care",
        "location": "Kochi",
        "experience_years": 10,
        "services": [
            ("Car Service", "Routine vehicle inspection and scheduled maintenance service.", "Car Service", "2500.00", 120),
        ],
    },
    {
        "key": "lens-light",
        "name": "Lens & Light Photography",
        "location": "Kochi",
        "experience_years": 7,
        "services": [
            ("Portrait Photography", "A one-hour portrait session with edited digital photographs.", "Photography", "4000.00", 60),
        ],
    },
    {
        "key": "webnest",
        "name": "WebNest Digital",
        "location": "Kochi",
        "experience_years": 6,
        "services": [
            ("Website Development Consultation", "A planning session to scope a small business website.", "Website Development", "1200.00", 30),
        ],
    },
]


class Command(BaseCommand):
    help = "Create local-only sample categories, providers and services for assessment demos."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo records can only be created while DEBUG=True.")

        demo_password = get_random_string(20)
        created_provider_emails = []
        created_services = 0
        weekdays = [(day, time(9, 0), time(17, 0)) for day in range(5)]
        weekdays.append((5, time(10, 0), time(14, 0)))

        with transaction.atomic():
            categories = [
                ("Home Cleaning", "home-cleaning"),
                ("Plumbing", "plumbing"),
                ("Electrical", "electrical"),
                ("Appliance Repair", "appliance-repair"),
                ("Laptop & Computer Repair", "laptop-computer-repair"),
                ("AC Service", "ac-service"),
                ("Car Service", "car-service"),
                ("Photography", "photography"),
                ("Website Development", "website-development"),
            ]
            category_by_slug = {}
            for name, slug in categories:
                category_by_slug[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})

            for provider_data in PROVIDERS:
                email = f"demo+{provider_data['key']}@example.test"
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={"role": User.Role.PROVIDER, "first_name": provider_data["name"], "phone": "+919876543210"},
                )
                if created:
                    user.set_password(demo_password)
                    user.save(update_fields=["password"])
                    created_provider_emails.append(email)
                elif user.role != User.Role.PROVIDER:
                    raise CommandError(f"{email} already exists with a non-provider role.")

                profile, _ = ProviderProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "display_name": provider_data["name"],
                        "description": f"Local service provider based in {provider_data['location']}, serving the neighbourhood by appointment.",
                        "location": provider_data["location"],
                        "experience_years": provider_data["experience_years"],
                    },
                )
                for weekday, start_time, end_time in weekdays:
                    WeeklyAvailability.objects.get_or_create(
                        provider=profile,
                        weekday=weekday,
                        defaults={"start_time": start_time, "end_time": end_time},
                    )

                for name, description, category_name, price, duration in provider_data["services"]:
                    category_slug = next(slug for category, slug in categories if category == category_name)
                    _, created = Service.objects.get_or_create(
                        provider=profile,
                        name=name,
                        defaults={
                            "category": category_by_slug[category_slug],
                            "description": description,
                            "location": provider_data["location"],
                            "price": Decimal(price),
                            "duration_minutes": duration,
                            "is_active": True,
                        },
                    )
                    created_services += int(created)

        self.stdout.write(self.style.SUCCESS(f"Demo data ready: {len(PROVIDERS)} providers, {created_services} new services."))
        if created_provider_emails:
            self.stdout.write("New demo provider logins (local development only):")
            for email in created_provider_emails:
                self.stdout.write(f"  {email}")
            self.stdout.write(f"Shared temporary password: {demo_password}")
            self.stdout.write("Change or remove these accounts before deploying or sharing the database.")
        else:
            self.stdout.write("Existing demo provider accounts were left unchanged; their original passwords are still in effect.")
