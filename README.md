# BookMyService

BookMyService is a Django web application for discovering local services and managing customer bookings, provider schedules, and reviews. It uses Django templates for the interface, SQLite for local development, and PostgreSQL for production.

## Features

- Customers and providers can register with email and password. Public registration does not allow users to create administrator accounts.
- Responsive landing page with a lavender and purple service-booking design, database-backed search, popular categories, and category photography.
- Dedicated `/explore/` catalog with category shortcuts, provider/location/price/rating/working-day filters, sorting, grid/list views, and customer favourites.
- Customers can search by keyword, category, provider, location, price, rating, and provider working day, then select an available start time and request a booking.
- Service detail pages show provider hours, customer feedback, other listings from the provider, and similar active services.
- Providers can manage their profile, weekly availability, services, blocked time ranges, and booking status transitions.
- Administrators have an operations dashboard with booking and user tables, provider review actions, category and user charts, and links to Django Admin.
- Reviews are rated from 1–5, limited to the customer after completion, and unique per booking.
- Booking time and price are stored on the booking record so later service edits do not rewrite booking history.
- Customers can save service/provider favourites, view booking notifications, and download access-controlled PDF booking confirmations.
- Booking references, transition timestamps, repeated-submit protection, overlap checks, and customer/provider history are database-backed.
- Provider matching uses location, budget, schedule, rating, and verification filters, with a fit score and reason breakdown. No runtime AI is used.
- A development-only `seed_demo_data` command creates example providers and services for local demonstrations.
- Staff can verify providers and review booking, category, service, and status metrics.

## Technology Stack

- Python 3.11+
- Django 5.x
- SQLite for local development
- PostgreSQL for production
- Django templates
- Bootstrap 5
- HTML, CSS, and JavaScript

## Project Structure

```text
config/       Settings, URL routing, ASGI/WSGI, middleware
accounts/     Custom user, provider profile, weekly availability, registration
services/     Service catalog, filtering, provider service management
bookings/     Booking model, lifecycle, booking and rescheduling rules
reviews/      Review model, form, and customer workflow
templates/    Shared UI, catalog, dashboards, and forms
static/       Responsive application styling
```

## Data Relationships

- A user has a role; a provider user has one provider profile.
- A provider profile has weekly availability rows and services.
- A service belongs to one category and provider.
- A booking points to a customer and service and stores start/end time, price, and duration snapshots.
- A review belongs to a booking and its author.
- User and service records referenced by bookings use protective deletion behavior. Deactivate accounts or services to remove them from new discovery without erasing history.

## Local Setup (Windows / PowerShell)

### Prerequisites

Install Python 3.11 or newer. Run the following commands from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo_data
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py runserver
```

Skip virtual-environment creation if `.venv` already exists. Skip copying `.env.example` if `.env` already exists, and skip `createsuperuser` if an administrator account already exists.

If PowerShell blocks environment activation, omit the activation command and use `.\.venv\Scripts\python.exe` instead of `python`.

Keep the terminal running `runserver` open while using the app. Stop the server with `Ctrl+C`.

Open `http://127.0.0.1:8000/`. Django Admin is available at `/admin/`. Provider profile and hours are available at `/accounts/provider/settings/`.

The `seed_demo_data` command is for local assessment demonstrations only and requires `DEBUG=True`. It creates example provider accounts and services and prints generated demo credentials. Do not deploy these demo accounts or use them for real users. The command is optional; you can create accounts and services manually.

The local `.env` file is loaded unless a variable is already defined in the process environment. The example configuration enables `DEBUG=True` for local HTTP development. For production, use `DEBUG=False`, a private random `SECRET_KEY` of at least 50 characters, exact allowed hostnames, and a configured server database.

**Never commit `.env` or other secrets to Git.**

## Configuration

Use only the variables required for your environment.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django signing key; use a private random value outside local development. |
| `DEBUG` | Set to `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames, if configured explicitly. |
| `DATABASE_URL` | Optional PostgreSQL connection URL. When unset, the project normally uses SQLite unless another database engine is configured. |
| `SQLITE_DB_PATH` | Optional SQLite database path, useful when working on a separate database copy. |
| `DB_SSLMODE` | PostgreSQL SSL mode; production deployments should use `require`. |
| `DB_ENGINE` | Set to `mysql` when using the optional MySQL configuration. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL connection details when `DB_ENGINE=mysql`. |
| `TIME_ZONE` | Application timezone; defaults to `Asia/Kolkata`. |
| `SITE_URL` | Optional public base URL used in booking emails. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP connection settings. |
| `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` | SMTP transport and sender settings. |
| `EMAIL_BACKEND` | Optional Django email backend override; local development defaults to the console backend. |
| `SECURE_SSL_REDIRECT` | HTTPS redirect setting; enabled by default when `DEBUG=False`. |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob token for persistent public service and provider images. Keep it secret. |
| `CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins for custom domains or cross-origin form posts. |

With `DATABASE_URL` unset, the project normally uses `db.sqlite3`. Uploaded images are stored under `media/` during local development. Production deployments should use durable object storage for uploads and a managed PostgreSQL database.

## Deploy to Vercel

The project is configured for Vercel deployment using `manage.py`, `config.wsgi:application`, `requirements.txt`, and Django static-file collection. Review the current Vercel project settings before deployment.

### Required Setup

1. Push approved project changes to the connected Git repository.
2. Create or select the Vercel project connected to that repository.
3. Connect a Vercel Blob store for public service and provider profile images.
4. Configure the required environment variables in Vercel Settings → Environment Variables for the appropriate Preview and Production environments.
5. Ensure `DATABASE_URL` points to the intended managed PostgreSQL database and `DB_SSLMODE=require`.
6. Redeploy after changing environment variables.

### Production Environment Variables

| Variable | Value |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | A private random value generated securely; never publish it. |
| `DATABASE_URL` | The pooled PostgreSQL connection URL for the production database. |
| `DB_SSLMODE` | `require` |
| `BLOB_READ_WRITE_TOKEN` | Token supplied by the Vercel Blob integration. |
| `SITE_URL` | Optional production URL, including `https://`. |
| `CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins for custom domains or cross-origin form posts. |

The current settings derive Vercel hostnames from Vercel system environment variables. If you explicitly set `ALLOWED_HOSTS`, include every hostname the app must serve. Same-origin forms on the Vercel project domain generally do not need an additional trusted origin; configure `CSRF_TRUSTED_ORIGINS` for custom or cross-origin HTTPS forms.

### Database and Media Migration

Do not assume the local `db.sqlite3` database has already been copied to PostgreSQL. Before migrating data, identify the source of truth, create a separate backup, and work on a copy of the source database. Keep exported fixtures private because they may contain user records and password hashes.

The following commands illustrate exporting a copy of the local SQLite database:

```powershell
Copy-Item .\db.sqlite3 .\db.vercel-export.sqlite3
$env:DB_ENGINE = "sqlite"
$env:DATABASE_URL = ""
$env:SQLITE_DB_PATH = "$PWD\db.vercel-export.sqlite3"
python manage.py migrate --noinput
python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --indent 2 --output .\vercel-data.json
```

Apply the current schema migrations to the destination database before loading a fixture. Load data and migrate media only after confirming that the active environment points to the intended destination database:

```powershell
python manage.py migrate --noinput
python manage.py loaddata .\vercel-data.json
python manage.py migrate_media_to_blob
```

These commands are examples, not a substitute for verifying the current database configuration. Set the destination PostgreSQL `DATABASE_URL`, production `SECRET_KEY`, `DEBUG=False`, and Blob token securely in the environment.

Verify source and destination record counts, sign-in, image URLs, registration, booking conflicts, and CSRF-protected forms before relying on the deployment. The media migration command requires the fixture to be loaded and source media files to be present. It updates image fields in the target database and does not delete original local media files.

Run database migrations as a deliberate one-off step after backing up the target database. Do not put migrations into a Vercel build command that may run for multiple Preview and Production deployments.

The booking migrations include a PostgreSQL exclusion constraint using `btree_gist`. Verify that the destination database allows the required extension and that migrations complete successfully.

Vercel, managed database, and object-storage quotas and terms can change. Check the provider dashboards for current limits and confirm that the deployment is appropriate for your intended use.

## Booking and Concurrency Design

Booking creation, rescheduling, and status transitions use database transactions and recheck availability while holding a provider-level lock. MySQL and PostgreSQL use `select_for_update()`; SQLite uses a provider lock-version write because SQLite ignores row-level `select_for_update()`.

The overlap rule is:

`existing.start < requested.end AND existing.end > requested.start`

Adjacent intervals are allowed, while exact and partial overlaps are rejected. Pending, confirmed, and in-progress bookings occupy a time slot; rejected and cancelled bookings release it.

Rescheduling checks the new interval while holding the provider lock and preserves the original booking if the operation fails.

Database safeguards vary by engine. The MySQL migration `bookings.0005_mysql_booking_overlap_triggers` installs insert/update triggers for overlapping active bookings and prevents changing a service's provider after bookings exist.

PostgreSQL migration `bookings.0004_booking_provider_lock_and_more` installs a GiST exclusion constraint using `btree_gist`; the database must permit that extension. SQLite does not provide a cross-row interval constraint, so its protection relies on the application's transaction service.

## Email, Receipts, and Provider Earnings

Booking request, status, cancellation, and rescheduling emails are queued after the booking transaction commits. During local development, the default console email backend prints email content in the runserver terminal. Configure SMTP variables to send real emails. Missing recipient details or a mail-server error does not undo a booking.

Customers can download access-controlled PDF booking confirmations. Providers can view estimates based on completed booking prices in the Earnings area. These figures represent booking value, not a payout statement, and do not subtract fees, refunds, or taxes.

## Security Notes

This assessment version uses authenticated Django views and forms rather than a separate REST API. Django CSRF middleware protects state-changing forms, ORM queries avoid raw SQL string construction, password validators and Django password hashers protect credentials, and server-side object scoping checks customer/provider ownership.

Public registration permits customer and provider roles only; administrator access is provisioned separately.

Production settings require explicit hosts, a strong secret, and a server database. When `DEBUG=False`, production settings enable secure cookies, HSTS, HTTPS redirection, and content-type protection. Custom 403, 404, and 500 pages prevent Django debug pages from being served in production.

Keep `.env`, database exports, credentials, and tokens out of Git.

## Tests

Run these commands from the repository root:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --settings=config.test_settings
```

The test suite covers booking interval conflicts, cancelled-slot reuse, booking lifecycle permissions, the customer cancellation cutoff, email notifications, PDF ownership, provider earnings scoping, completed/unique review rules, administrator provider-review permissions, and dashboard search/filter/pagination.

The concurrent test class is `bookings.tests.RelationalBookingRaceTests`. It covers simultaneous HTTP booking requests for one slot, service-level booking/rescheduling/cancellation races, different slots, and a direct insert against the database guard.

Project notes report these and related tests passing against MySQL 8.0.33; the direct-constraint test is skipped on SQLite. PostgreSQL migration, concurrency, and live deployment checks must be run against the actual production database before claiming those checks are complete.

## Screen Recording Outline (5–10 Minutes)

Record a walkthrough of the actual application using your own voice:

1. Introduce the catalog and demonstrate search and filters.
2. Register a customer, open a service, request a future time, and inspect the customer dashboard.
3. Sign in as a provider, edit the profile and weekly hours, add a service, and update a booking status.
4. Return as the customer to cancel or reschedule a booking and submit a review after completion.
5. Demonstrate the overlap warning for a conflicting booking and the cancellation cutoff.
6. Open the administrator dashboard and Django Admin to manage categories and inspect bookings.

Run `seed_demo_data` locally if you need demonstration data. Use the credentials printed by the command only on your local machine. Never show `.env`, secret values, database exports, or demo passwords in the recording.

## Known Limitations

- The booking form generates start-time choices at 30-minute intervals for one selected date; it does not provide a month-grid calendar.
- There is no scheduled reminder worker.
- Provider management and dashboards are template-based; a separate REST API is not implemented.
- Tax and commission calculations are not implemented.
- Location matching uses provider/service location text; geospatial service-area data is not part of the current schema.
- Administrator provider verification is manually managed; no external identity-verification service is connected.
- PostgreSQL concurrency verification, browser/responsive review, and production deployment checks must be completed against the actual target environment.
- Production uploads require durable object storage; local media files are not a production storage solution.


| Separate REST API | Not implemented; server-rendered Django flows are used. |
