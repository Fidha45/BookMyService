from decimal import Decimal
from datetime import time
from django.db import migrations
from django.contrib.auth.hashers import make_password

CATEGORIES = [
    ("Home Cleaning", "home-cleaning"),
    ("Plumbing", "plumbing"),
    ("Electrical", "electrical"),
    ("Appliance Repair", "appliance-repair"),
    ("Beauty & Wellness", "beauty-wellness"),
    ("Painting", "painting"),
    ("Moving & Packing", "moving-packing"),
    ("Gardening", "gardening"),
    ("Laptop & Computer Repair", "laptop-computer-repair"),
    ("AC Service", "ac-service"),
    ("Car Service", "car-service"),
    ("Photography", "photography"),
    ("Website Development", "website-development"),
    ("Carpentry", "carpentry"),
    ("Home Renovation", "home-renovation"),
    ("Pest Control", "pest-control"),
]

PROVIDERS = [
    {
        "email": "demo+abc-tech@example.test",
        "name": "ABC Tech Services",
        "location": "Kochi",
        "experience_years": 8,
        "phone": "+919876543210",
        "services": [
            ("Laptop Repair", "Laptop diagnostics, hardware repair and software troubleshooting.", "laptop-computer-repair", "800.00", 60),
        ],
    },
    {
        "email": "demo+cool-care@example.test",
        "name": "CoolCare Home Services",
        "location": "Kochi",
        "experience_years": 6,
        "phone": "+919876543210",
        "services": [
            ("AC Service", "AC inspection, filter cleaning and routine performance service.", "ac-service", "1500.00", 90),
            ("Appliance Repair", "Diagnosis and repair for common household appliances.", "appliance-repair", "650.00", 60),
        ],
    },
    {
        "email": "demo+home-essentials@example.test",
        "name": "Home Essentials",
        "location": "Kochi",
        "experience_years": 5,
        "phone": "+919876543210",
        "services": [
            ("Home Cleaning", "A thorough scheduled cleaning for kitchens, living rooms and bedrooms.", "home-cleaning", "900.00", 120),
            ("Plumbing Visit", "Inspection and repair for common tap, drain and pipe issues.", "plumbing", "600.00", 60),
            ("Electrical Service", "Safe inspection and repair of common household electrical issues.", "electrical", "500.00", 60),
            ("Carpentry Service", "Carpentry service for common home repairs and installation work. Final scope is confirmed with the provider before work begins.", "carpentry", "800.00", 60),
            ("Home Renovation Consultation", "A consultation to discuss home renovation needs, scope, and next steps with the provider.", "home-renovation", "1200.00", 60),
            ("Painting Service", "Painting service for a small area. The work area and final scope should be confirmed with the provider before booking.", "painting", "1500.00", 120),
            ("Pest Control Service", "Pest control service for common household needs. Treatment details and suitability should be confirmed with the provider before service.", "pest-control", "1200.00", 60),
        ],
    },
    {
        "email": "demo+city-auto@example.test",
        "name": "City Auto Care",
        "location": "Kochi",
        "experience_years": 10,
        "phone": "+919876543210",
        "services": [
            ("Car Service", "Routine vehicle inspection and scheduled maintenance service.", "car-service", "2500.00", 120),
        ],
    },
    {
        "email": "demo+lens-light@example.test",
        "name": "Lens & Light Photography",
        "location": "Kochi",
        "experience_years": 7,
        "phone": "+919876543210",
        "services": [
            ("Portrait Photography", "A one-hour portrait session with edited digital photographs.", "photography", "4000.00", 60),
        ],
    },
    {
        "email": "demo+webnest@example.test",
        "name": "WebNest Digital",
        "location": "Kochi",
        "experience_years": 6,
        "phone": "+919876543210",
        "services": [
            ("Website Development Consultation", "A planning session to scope a small business website.", "website-development", "1200.00", 30),
        ],
    },
]


def restore_catalog_data(apps, schema_editor):
    db = schema_editor.connection.alias
    Category = apps.get_model("services", "Category")
    Service = apps.get_model("services", "Service")
    User = apps.get_model("accounts", "User")
    ProviderProfile = apps.get_model("accounts", "ProviderProfile")
    WeeklyAvailability = apps.get_model("accounts", "WeeklyAvailability")

    category_map = {}
    for name, slug in CATEGORIES:
        cat, _ = Category.objects.using(db).get_or_create(slug=slug, defaults={"name": name})
        category_map[slug] = cat

    weekdays = [(day, time(9, 0), time(17, 0)) for day in range(5)]
    weekdays.append((5, time(10, 0), time(14, 0)))

    for p_data in PROVIDERS:
        email = p_data["email"]
        user, _ = User.objects.using(db).get_or_create(
            email=email,
            defaults={
                "role": "provider",
                "first_name": p_data["name"],
                "phone": p_data["phone"],
                "is_active": True,
                "password": make_password("DemoProvider@12345"),
            },
        )
        profile, _ = ProviderProfile.objects.using(db).get_or_create(
            user=user,
            defaults={
                "display_name": p_data["name"],
                "description": f"Local service provider based in {p_data['location']}, serving the neighbourhood by appointment.",
                "location": p_data["location"],
                "experience_years": p_data["experience_years"],
                "is_verified": True,
                "approval_status": "approved",
            },
        )
        for weekday, start_time, end_time in weekdays:
            WeeklyAvailability.objects.using(db).get_or_create(
                provider=profile,
                weekday=weekday,
                defaults={"start_time": start_time, "end_time": end_time},
            )

        for name, description, cat_slug, price, duration in p_data["services"]:
            cat = category_map[cat_slug]
            Service.objects.using(db).get_or_create(
                provider=profile,
                name=name,
                defaults={
                    "category": cat,
                    "description": description,
                    "location": p_data["location"],
                    "price": Decimal(price),
                    "duration_minutes": duration,
                    "is_active": True,
                },
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("services", "0006_category_admin_labels"),
        ("accounts", "0006_providerprofile_booking_lock_version"),
    ]

    operations = [
        migrations.RunPython(restore_catalog_data, noop_reverse),
    ]
