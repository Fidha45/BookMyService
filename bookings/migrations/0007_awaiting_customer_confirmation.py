from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.contrib.postgres.fields.ranges import RangeOperators
from django.db import migrations, models
from django.db.models import F, Func, Q, Value


OLD_OCCUPYING_STATUSES = ("pending", "confirmed", "in_progress")
OCCUPYING_STATUSES = OLD_OCCUPYING_STATUSES + ("awaiting_customer_confirmation",)


def _overlap_constraint(statuses):
    return ExclusionConstraint(
        name="exclude_overlapping_active_provider_bookings",
        expressions=[
            ("provider_lock", RangeOperators.EQUAL),
            (
                Func(
                    F("start_at"), F("end_at"), Value("[)"),
                    function="TSTZRANGE", output_field=DateTimeRangeField(),
                ),
                RangeOperators.OVERLAPS,
            ),
        ],
        condition=Q(status__in=statuses),
    )


def _install_mysql_booking_triggers(schema_editor, statuses):
    if schema_editor.connection.vendor != "mysql":
        return
    status_sql = ", ".join(f"'{status}'" for status in statuses)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS bookings_reject_overlap_before_insert")
        cursor.execute("DROP TRIGGER IF EXISTS bookings_reject_overlap_before_update")
        cursor.execute(f"""
            CREATE TRIGGER bookings_reject_overlap_before_insert
            BEFORE INSERT ON bookings_booking
            FOR EACH ROW
            BEGIN
              DECLARE expected_provider_id BIGINT;
              SELECT provider_id INTO expected_provider_id
                FROM services_service WHERE id = NEW.service_id;
              IF expected_provider_id IS NULL OR NEW.provider_lock_id <> expected_provider_id THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking provider does not match its service';
              END IF;
              SELECT id INTO expected_provider_id
                FROM accounts_providerprofile WHERE id = expected_provider_id FOR UPDATE;
              IF NEW.status IN ({status_sql}) AND EXISTS (
                SELECT 1 FROM bookings_booking b
                WHERE b.provider_lock_id = expected_provider_id
                  AND b.status IN ({status_sql})
                  AND b.start_at < NEW.end_at AND b.end_at > NEW.start_at
              ) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking interval overlaps an active booking';
              END IF;
            END
        """)
        cursor.execute(f"""
            CREATE TRIGGER bookings_reject_overlap_before_update
            BEFORE UPDATE ON bookings_booking
            FOR EACH ROW
            BEGIN
              DECLARE expected_provider_id BIGINT;
              SELECT provider_id INTO expected_provider_id
                FROM services_service WHERE id = NEW.service_id;
              IF expected_provider_id IS NULL OR NEW.provider_lock_id <> expected_provider_id THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking provider does not match its service';
              END IF;
              SELECT id INTO expected_provider_id
                FROM accounts_providerprofile WHERE id = expected_provider_id FOR UPDATE;
              IF NEW.status IN ({status_sql}) AND EXISTS (
                SELECT 1 FROM bookings_booking b
                WHERE b.provider_lock_id = expected_provider_id
                  AND b.id <> NEW.id
                  AND b.status IN ({status_sql})
                  AND b.start_at < NEW.end_at AND b.end_at > NEW.start_at
              ) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking interval overlaps an active booking';
              END IF;
            END
        """)


def update_overlap_protection(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        Booking = apps.get_model("bookings", "Booking")
        schema_editor.remove_constraint(Booking, _overlap_constraint(OLD_OCCUPYING_STATUSES))
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        schema_editor.add_constraint(Booking, _overlap_constraint(OCCUPYING_STATUSES))
    elif schema_editor.connection.vendor == "mysql":
        _install_mysql_booking_triggers(schema_editor, OCCUPYING_STATUSES)


def restore_overlap_protection(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        Booking = apps.get_model("bookings", "Booking")
        schema_editor.remove_constraint(Booking, _overlap_constraint(OCCUPYING_STATUSES))
        schema_editor.add_constraint(Booking, _overlap_constraint(OLD_OCCUPYING_STATUSES))
    elif schema_editor.connection.vendor == "mysql":
        _install_mysql_booking_triggers(schema_editor, OLD_OCCUPYING_STATUSES)


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0006_mysql_safe_unique_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("in_progress", "In progress"),
                    ("awaiting_customer_confirmation", "Awaiting customer confirmation"),
                    ("completed", "Completed"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=32,
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(update_overlap_protection, restore_overlap_protection)],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="booking",
                    name="exclude_overlapping_active_provider_bookings",
                ),
                migrations.AddConstraint(
                    model_name="booking",
                    constraint=_overlap_constraint(OCCUPYING_STATUSES),
                ),
            ],
        ),
    ]
