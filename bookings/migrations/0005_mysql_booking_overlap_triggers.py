from django.db import migrations


INSERT_TRIGGER = """
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
  IF NEW.status IN ('pending', 'confirmed', 'in_progress') AND EXISTS (
    SELECT 1 FROM bookings_booking b
    WHERE b.provider_lock_id = expected_provider_id
      AND b.status IN ('pending', 'confirmed', 'in_progress')
      AND b.start_at < NEW.end_at AND b.end_at > NEW.start_at
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking interval overlaps an active booking';
  END IF;
END
"""

UPDATE_TRIGGER = """
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
  IF NEW.status IN ('pending', 'confirmed', 'in_progress') AND EXISTS (
    SELECT 1 FROM bookings_booking b
    WHERE b.provider_lock_id = expected_provider_id
      AND b.id <> NEW.id
      AND b.status IN ('pending', 'confirmed', 'in_progress')
      AND b.start_at < NEW.end_at AND b.end_at > NEW.start_at
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking interval overlaps an active booking';
  END IF;
END
"""

SERVICE_PROVIDER_TRIGGER = """
CREATE TRIGGER services_keep_booked_provider_before_update
BEFORE UPDATE ON services_service
FOR EACH ROW
BEGIN
  IF OLD.provider_id <> NEW.provider_id AND EXISTS (
    SELECT 1 FROM bookings_booking b WHERE b.service_id = OLD.id
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A service provider cannot change after bookings exist';
  END IF;
END
"""


def install_mysql_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(INSERT_TRIGGER)
        cursor.execute(UPDATE_TRIGGER)
        cursor.execute(SERVICE_PROVIDER_TRIGGER)


def remove_mysql_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER IF EXISTS bookings_reject_overlap_before_insert")
        cursor.execute("DROP TRIGGER IF EXISTS bookings_reject_overlap_before_update")
        cursor.execute("DROP TRIGGER IF EXISTS services_keep_booked_provider_before_update")


class Migration(migrations.Migration):
    dependencies = [("bookings", "0004_booking_provider_lock_and_more")]

    operations = [
        migrations.RunPython(install_mysql_triggers, remove_mysql_triggers),
    ]
