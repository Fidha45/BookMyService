from django.db import migrations, models
from django.db.models import Count, F, Value


ACTIVE_PAYMENT_STATUSES = ("created", "pending", "succeeded")


def validate_existing_unique_keys(apps, schema_editor):
    """Fail safely instead of deleting records if a backend previously skipped indexes."""
    alias = schema_editor.connection.alias
    Payment = apps.get_model("bookings", "Payment")

    duplicate_payment = (
        Payment.objects.using(alias)
        .filter(status__in=ACTIVE_PAYMENT_STATUSES)
        .values("booking_id")
        .annotate(row_count=Count("pk"))
        .filter(row_count__gt=1)
        .order_by("booking_id")
        .first()
    )
    if duplicate_payment:
        raise RuntimeError(
            "Cannot add one-active-payment-per-booking protection: "
            f"booking {duplicate_payment['booking_id']} has multiple active payment rows. "
            "Resolve those records without deleting payment history, then rerun migrations."
        )

    if schema_editor.connection.vendor == "mysql":
        Booking = apps.get_model("bookings", "Booking")
        table = schema_editor.quote_name(Booking._meta.db_table)
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT a.id, b.id FROM {table} a JOIN {table} b "
                "ON a.provider_lock_id = b.provider_lock_id AND a.id < b.id "
                "AND a.status IN ('pending', 'confirmed', 'in_progress') "
                "AND b.status IN ('pending', 'confirmed', 'in_progress') "
                "AND a.start_at < b.end_at AND a.end_at > b.start_at LIMIT 1"
            )
            overlap = cursor.fetchone()
        if overlap:
            raise RuntimeError(
                "Cannot finalize MySQL booking conflict protection: active bookings "
                f"{overlap[0]} and {overlap[1]} already overlap. Review and resolve those "
                "records without deleting booking history, then rerun migrations."
            )


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0005_mysql_booking_overlap_triggers"),
        ("services", "0004_assessment_categories"),
    ]

    operations = [
        migrations.RunPython(validate_existing_unique_keys, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="payment",
            name="one_active_payment_per_booking",
        ),
        migrations.AddField(
            model_name="payment",
            name="active_booking_id",
            field=models.GeneratedField(
                db_persist=True,
                expression=models.Case(
                    models.When(
                        status__in=ACTIVE_PAYMENT_STATUSES,
                        then=F("booking_id"),
                    ),
                    default=Value(None, output_field=models.BigIntegerField()),
                    output_field=models.BigIntegerField(),
                ),
                output_field=models.BigIntegerField(null=True),
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=("active_booking_id",),
                name="one_active_payment_per_booking",
            ),
        ),
    ]
