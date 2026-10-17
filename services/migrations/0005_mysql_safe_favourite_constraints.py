from django.db import migrations, models
from django.db.models import Count


def validate_existing_favourites(apps, schema_editor):
    Favourite = apps.get_model("services", "Favourite")
    alias = schema_editor.connection.alias

    duplicate_service = (
        Favourite.objects.using(alias)
        .filter(service__isnull=False)
        .values("customer_id", "service_id")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
        .order_by("customer_id", "service_id")
        .first()
    )
    if duplicate_service:
        raise RuntimeError(
            "Cannot add unique service-favourite protection: duplicate rows exist for "
            f"customer {duplicate_service['customer_id']} and service {duplicate_service['service_id']}. "
            "Review the rows and rerun migrations."
        )

    duplicate_provider = (
        Favourite.objects.using(alias)
        .filter(provider__isnull=False)
        .values("customer_id", "provider_id")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
        .order_by("customer_id", "provider_id")
        .first()
    )
    if duplicate_provider:
        raise RuntimeError(
            "Cannot add unique provider-favourite protection: duplicate rows exist for "
            f"customer {duplicate_provider['customer_id']} and provider {duplicate_provider['provider_id']}. "
            "Review the rows and rerun migrations."
        )


class Migration(migrations.Migration):
    dependencies = [("services", "0004_assessment_categories")]

    operations = [
        migrations.RunPython(validate_existing_favourites, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="favourite",
            name="unique_customer_favourite_service",
        ),
        migrations.RemoveConstraint(
            model_name="favourite",
            name="unique_customer_favourite_provider",
        ),
        migrations.AddConstraint(
            model_name="favourite",
            constraint=models.UniqueConstraint(
                fields=("customer", "service"),
                name="unique_customer_favourite_service",
            ),
        ),
        migrations.AddConstraint(
            model_name="favourite",
            constraint=models.UniqueConstraint(
                fields=("customer", "provider"),
                name="unique_customer_favourite_provider",
            ),
        ),
    ]
