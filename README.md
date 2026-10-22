# BookMyService

BookMyService is a Django application for discovering local services and managing customer bookings, provider schedules and reviews. Pages are rendered by Django templates; SQLite is configured for a local learning setup and PostgreSQL is supported for production.

## Features

- Customers and providers can register with email and password. A public role selector never offers administrator access.
- The public landing page uses a responsive lavender and purple service-booking layout, with database-backed search, popular categories, and optimized local category photography.
- The dedicated `/explore/` catalog has responsive category shortcuts, provider/location/price/rating/working-day filters, real booking/rating/price/newest sorting, grid/list views, and customer favourites.
- Customers search by keywords, category, provider, location, price, rating and provider working day, then choose a generated start time for a date and request a booking.
- Service detail pages include provider hours, customer feedback, other listings from the provider, and similar active services matched by category or location.
- Providers manage their profile, weekly hours, services, and booking status transitions.
- Administrators use a responsive operations dashboard with live totals, searchable/paginated booking and user tables, provider review actions, category and user charts, captured payment totals, and links to Django Admin.
- Reviews are unique per booking, rated 1–5, and restricted to the customer after completion.
- Booking time and price are copied onto the booking record so service edits do not rewrite history.
- Customers can save service/provider favourites, see persistent booking notifications, and download access-controlled PDF receipts.
- Providers can block specific future date/time ranges in addition to recurring weekly hours.
- Booking references, transition timestamps, repeated-submit protection, overlap checks, and customer/provider history are database-backed.
- Provider matching uses deterministic location, budget, schedule, rating, and verification filters, with a visible fit score and reason breakdown for every result. No runtime AI is used.
- A development-only `seed_demo_data` command creates realistic example providers and services for search, booking and dashboard demonstrations.
- Razorpay order creation, server-side signature and captured-amount verification, and signed webhook processing are configurable; payments stay unconfirmed until verified.
- Staff can verify providers and review date-filtered booking, category, service, status, and payment metrics.

## Stack and structure

Python 3.11+, Django 5.x, SQLite locally, PostgreSQL in production, Django templates, Bootstrap 5 and a small custom stylesheet.

```text
config/       settings, URL routing, ASGI/WSGI, middleware
accounts/     custom user, provider profile, weekly availability, registration
services/     service catalog, filtering, provider service management
bookings/     booking model, lifecycle, booking and rescheduling rules
reviews/      review model, form and customer workflow
templates/    shared UI, catalog, dashboards and forms
static/       responsive application styling
```

## Data relationships

- `User` has a role; a provider user has one `ProviderProfile`.
- A provider profile has weekly availability rows and services.
- A service belongs to one category and provider.
- A booking points to a customer and service, with stored start/end, price and duration snapshots.
- A review has a one-to-one relationship with a booking and points to its author.
- User and service records referenced by bookings use protective deletion behavior. Deactivate accounts/services to remove them from new discovery without erasing history.

## Local setup

Prerequisites: Python 3.11 or newer. From the repository root in PowerShell:

```powershell
py -m venv .venv # skip if .venv already exists
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env # only if .env does not already exist
python manage.py migrate
python manage.py seed_demo_data # optional local assessment data; requires DEBUG=True
python manage.py collectstatic --noinput
python manage.py createsuperuser # only if you do not already have an admin
python manage.py runserver
```

If PowerShell blocks activation, omit the activation line and replace `python` with `.\.venv\Scripts\python.exe`. Keep the `runserver` PowerShell window open while using the site. Stop it with `Ctrl+C`; run other management commands in a second PowerShell window.
Open http://127.0.0.1:8000/. Use `/admin/` to create categories before providers publish services. Provider profile and hours are at `/accounts/provider/settings/`. Create administrators with `createsuperuser`; never expose an admin role in public registration.

`seed_demo_data` is for local assessment demos only and refuses to run with `DEBUG=False`. On first run, it creates six demo provider accounts and nine example services from the brief, then prints their emails and a generated temporary password. Do not use or deploy these demo accounts in production. The command is safe to rerun; it leaves existing passwords and service records unchanged.

The local `.env` file is read unless the process already defines the same variable. The checked-in example enables `DEBUG=True` for local HTTP development. Django defaults to `DEBUG=False` if the setting is absent; in that mode startup requires a private random `SECRET_KEY` of at least 50 characters, exact `ALLOWED_HOSTS`, and an explicit PostgreSQL or MySQL configuration. Replace the sample secret before using the app beyond local development.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django signing key; set a random value outside local development |
| `DEBUG` | Set `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `RENDER_EXTERNAL_HOSTNAME` | Automatically supplied by Render; used as the production allowed host, HTTPS proxy signal, and default `SITE_URL` |
| `DATABASE_URL` | Optional PostgreSQL URL (`postgresql://user:password@host:5432/db`) |
| `DB_SSLMODE` | Optional PostgreSQL SSL mode, defaults to `prefer` |
| `DB_ENGINE` | Optional `mysql` to use the MySQL connection variables below |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | MySQL connection details when `DB_ENGINE=mysql` |
| `TIME_ZONE` | Django timezone, defaults to `Asia/Kolkata` |
| `SITE_URL` | Optional public base URL used for links in booking emails |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP connection details |
| `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` | SMTP security, timeout, and sender settings |
| `EMAIL_BACKEND` | Optional Django email backend override; local development defaults to the console backend |
| `SECURE_SSL_REDIRECT` | Production HTTPS redirect (defaults on when `DEBUG=False`) |
| `RAZORPAY_KEY_ID` | Razorpay test/live key identifier |
| `RAZORPAY_KEY_SECRET` | Razorpay API secret, used only by the server |
| `RAZORPAY_WEBHOOK_SECRET` | Signing secret configured for the Razorpay webhook |

With `DATABASE_URL` unset, the project uses `db.sqlite3`. Uploaded images are stored under `media/` in development. Production deployments should use durable object storage for uploads and a managed PostgreSQL database.

## Deploy to Render

The repository includes a Render Blueprint in `render.yaml`. After pushing the project to a Git repository, create a Blueprint in Render and select that repository. The Blueprint provisions the web service and PostgreSQL database, installs `requirements-production.txt`, collects static files, applies database migrations at startup, and runs the app with Gunicorn. Render generates `SECRET_KEY` and supplies the database connection and public hostname; keep `DEBUG=False` in production.

`Procfile` provides the same Gunicorn web command for hosts that use Procfiles. `requirements-production.txt` includes the packages from `requirements.txt` plus Gunicorn. Local runserver logs match `*.log` in `.gitignore` and are not deployment files. Before accepting real provider uploads, configure durable object storage for `media/`; Render's service filesystem is not durable storage for user uploads.

Booking request, status, cancellation, and reschedule emails are queued after the booking transaction commits. For local development, the default console backend prints emails in the runserver terminal. Configure the SMTP variables above to deliver email; a missing recipient address or mail server error does not undo a booking. The customer dashboard's booking records include a downloadable PDF confirmation. Providers can open **Earnings** from the navigation or dashboard to see estimates based on completed booking prices; this is booking value, not a payout statement and does not subtract fees, refunds, or taxes.

## Booking and concurrency design

All new bookings, reschedules and status transitions are wrapped in `transaction.atomic()`. They serialize slot-affecting writes through the stable provider-profile row and recheck availability after acquiring the lock. MySQL and PostgreSQL use `select_for_update()`; SQLite increments a provider lock-version field as the first transaction write because SQLite ignores row-level `select_for_update()`. The overlap test is `existing.start < requested.end AND existing.end > requested.start`, allowing adjacent intervals while rejecting exact and partial overlaps. Pending, confirmed and in-progress bookings occupy time; rejected and cancelled bookings release it.

Database safeguards supplement the application lock. MySQL migration `bookings.0005_mysql_booking_overlap_triggers` installs insert/update triggers that lock the provider row and reject overlapping active intervals, and prevents changing a service's provider after bookings exist. MySQL enforces one active payment per booking through a unique index on a stored generated nullable key (`active_booking_id`); failed/refunded attempts produce `NULL`, so payment history remains. Favourite uniqueness uses ordinary unique indexes on `(customer, service)` and `(customer, provider)`. MySQL allows repeated `NULL` values in those indexes, so separate target types remain possible while duplicate targets are rejected; the favourite target check constraint also requires MySQL 8.0.16 or newer. PostgreSQL migration `bookings.0004_booking_provider_lock_and_more` installs a GiST exclusion constraint using `btree_gist`; a PostgreSQL deployment must apply migrations with permission to create that extension. SQLite has no cross-row interval constraint, so its guarantee applies to booking writes through the application transaction service; the independent-connection race tests exercise this lock strategy. Rescheduling checks the new interval while holding the provider lock, excluding its own old booking, then changes the interval in the same transaction; failures preserve the original booking.

## API, security and deployment

This assessment version uses authenticated Django views and forms rather than adding a separate REST API. Django's CSRF middleware protects state-changing forms, ORM queries avoid SQL string construction, password validators and Django's password hashers protect credentials, and server-side object scoping checks customer/provider ownership. Public registration only permits customer/provider roles; admin access is provisioned separately. Production settings require explicit hosts, a strong secret and a server database, and enable secure cookies, HSTS, HTTPS redirection, and content-type protection. Custom 403, 404, and 500 pages prevent Django's debug pages from being served when `DEBUG=False`. Keep `.env` out of Git. `requirements-production.txt` adds Gunicorn and `Procfile` starts `config.wsgi:application`.

### Render deployment preparation

The root `render.yaml` defines a Python web service and PostgreSQL database for a temporary assessment deployment. It builds static assets, runs migrations on service startup, generates the Django secret, derives the allowed host and HTTPS proxy settings from Render's `RENDER_EXTERNAL_HOSTNAME`, and uses the console email backend until SMTP credentials are added. After pushing this repository, create a Render Blueprint from it and review the resources before deploying. The included free Postgres plan expires 30 days after creation, so export data or upgrade before then; free web instances also sleep when idle. Uploaded media is not durable on a free web instance. The PostgreSQL booking exclusion-constraint migration must be verified on the created database before treating that deployment as double-booking safe.

After deployment, create the first administrator through the Render Shell with `python manage.py createsuperuser`, add categories and provider/service demo data, and verify registration, booking, provider approval, emails, and the PostgreSQL concurrency test. Configure SMTP and Razorpay test credentials separately if those integrations need to be demonstrated. The deployment has not yet been launched because this workspace has no GitHub or Render account connection.

## Tests

Tests cover booking interval conflicts, cancelled slot reuse, lifecycle permissions, the two-hour customer cancellation cutoff, email notifications, PDF ownership, provider earnings scoping, completed/unique review rules, administrator provider review permissions, and dashboard search/filter/pagination/payment totals.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --settings=config.test_settings
```

The concurrent tests are `bookings.tests.RelationalBookingRaceTests`; they cover simultaneous HTTP booking requests for one slot, direct service-level booking/reschedule/cancellation races, different slots, and a direct insert against the database guard. These tests and the payment/favourite uniqueness tests passed against MySQL 8.0.33. The direct-constraint test is skipped on SQLite, which has no cross-row interval constraint. PostgreSQL migration/constraint execution still needs verification against a PostgreSQL server. SQLite's booking conflict protection relies on the transaction service rather than a database interval constraint.

Razorpay setup is optional for browsing and booking. For test mode, add test credentials to the ignored local `.env`, configure a webhook at `/bookings/payments/razorpay/webhook/`, and set its signing secret in `RAZORPAY_WEBHOOK_SECRET`. Checkout/API calls were not tested with real credentials in this workspace.

## Screen recording outline (5–10 minutes)

Use the outline below to record a walkthrough of the real app in your own voice.

1. Introduce the catalog and search/filter results.
2. Register a customer, view a service, request a future time and inspect the customer dashboard.
3. Sign in as a provider, edit weekly hours/profile, add a service, and confirm/start/complete a request.
4. Return as customer to cancel or reschedule a booking and submit a completed-service review.
5. Show the slot conflict message for an overlapping request and the two-hour cancellation rule.
6. Open the administrator dashboard and Django Admin to manage categories and inspect bookings.

Run `seed_demo_data` locally to create demo accounts/services, then use the credentials printed by the command only on your local machine. The seed command is optional; alternatively create accounts and service data manually. Never show `.env`, secrets, or demo passwords in the recording.

## Known limitations and next steps

- The booking form generates 30-minute-spaced start choices for one selected date. Providers can add blocked periods, but there is no month-grid calendar or scheduled reminder worker.
- Provider management and dashboards are template based; there is no REST API.
- Refund processing and tax/commission calculations are not implemented. Receipts show the stored booking price and verified payment state without inventing fees.
- Location matching uses service/provider location text because the current schema has no geospatial service-area data.
- Administrator verification is a manually managed flag; no external identity verification is connected.
- PostgreSQL concurrency verification, browser/responsive review, and deployment validation remain to be run.
- Production uploads need durable object storage; local media files are not a production storage solution.
- A GitHub remote is configured. Public deployment and the candidate-recorded video are still pending.

## Assessment checklist

| Area | Status |
| --- | --- |
| Customer/provider registration, login, profile and role dashboards | Implemented; automated tests pass |
| Catalog, search, category/location/price filters and pagination | Implemented; automated tests pass |
| Provider services, weekly hours, blocked periods and booking actions | Implemented; automated tests pass |
| Booking snapshots/references, overlap checks, cancellation, reschedule, reviews | Implemented; automated tests pass |
| Concurrent double-booking protection | MySQL overlap triggers and provider-row locking; simultaneous HTTP test passed on local MySQL 8.0.33; PostgreSQL verification pending |
| Admin dashboard, reporting charts, provider verification and Django Admin | Implemented; system checks pass |
| PostgreSQL production configuration and security settings | Implemented; Render Blueprint prepared, live deployment pending |
| REST API | Not implemented; server-rendered flows used |
| PostgreSQL race-test run, public deployment, screen recording | Pending; requires PostgreSQL/deployment access and candidate-recorded video |
