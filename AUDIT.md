# BookMyService assessment audit

Audit date: 17 October 2026. This audit reflects the current source tree and the checks listed below. Passing Django tests verify application behavior on the configured local MySQL test database; they are not a substitute for a live Razorpay transaction or browser/device review.

## Requirement checklist

| Requirement | Status | Evidence / limitation |
| --- | --- | --- |
| Customer registration, login, logout, profile and role assignment | COMPLETED | Public registration restricts roles to customer/provider; account tests cover role tampering, duplicate email and deactivated sessions. |
| Browse, search, filter and view service details | COMPLETED | Catalog and detail views query active database records; service tests cover filters, sorting, details and empty/database-backed content. |
| Customer booking history, cancellation, rescheduling and receipts | COMPLETED | Customer dashboard is scoped to the signed-in customer; booking action and invoice views enforce ownership. Rules have automated tests. |
| Service provider dashboard and service management | COMPLETED | Provider dashboard and service edits are scoped to the owner; tests cover another provider's service access. |
| Provider availability and blocked periods | COMPLETED | Weekly hours and date blocks are persisted and validated by booking logic. Tests cover blocked and unavailable periods. |
| Provider booking actions and valid status transitions | COMPLETED | Transition logic checks actor, current status and valid transition; tests cover invalid customer status changes and cancellation cutoff. |
| Admin dashboard, Django Admin and provider review | COMPLETED | Responsive dashboard uses live aggregates and supports booking/user search, status/type filtering, pagination, and permission-checked provider approval/rejection. The separate Django Admin Services and Categories management pages retain model CRUD. Automated tests cover the workflows; manual browser review remains pending. |
| Booking overlap and simultaneous request protection | COMPLETED | MySQL row locks plus insert/update triggers enforce intervals; PostgreSQL has a GiST exclusion constraint; SQLite serializes application writes through a provider lock-version update. Concurrent create/reschedule tests passed on MySQL and create/reschedule races passed on SQLite. PostgreSQL execution remains pending. |
| Booking duration snapshots and safe rescheduling | COMPLETED | Booking stores price/duration; this audit fixed duration read before service lock and booking/provider lock inversion. Regression tests cover locked duration and completed-booking reschedule rejection. |
| Payment server-side signature and amount verification | PARTIALLY COMPLETED | Code verifies Razorpay signature, then fetches payment from Razorpay and checks order, amount, currency and capture status; mocked tests cover this. No real test credentials are configured. |
| Razorpay webhook validation and duplicate event handling | PARTIALLY COMPLETED | HMAC signature and captured amount/status checks are implemented; signed webhook test exists. Live delivery/retry behavior is not tested. |
| Payment status, cancellation and refunds | PARTIALLY COMPLETED | Payment is only marked succeeded after gateway confirmation; refunds are not implemented. A payment captured after a booking is cancelled requires manual reconciliation/refund. |
| Email notifications | COMPLETED | Booking/status emails use Django email settings, console backend in local DEBUG mode, and post-commit delivery; automated tests cover notifications and delivery failure. SMTP delivery is not verified. |
| Secure PDF booking confirmation | COMPLETED | PDF is generated from database records; customer/provider/staff authorization is enforced and tested against an unrelated customer. |
| Provider earnings dashboard | COMPLETED | Provider-scoped completed-booking totals and monthly history use stored booking prices; tests exclude other providers and incomplete bookings. It is an estimate, not a payout calculation. |
| CSRF, ORM input handling, object scoping, upload validation | COMPLETED | Django CSRF middleware and ORM are used; booking, service, invoice and profile flows contain server-side access checks; uploaded image forms validate type and size. |
| Production configuration | PARTIALLY COMPLETED | Production settings support HTTPS/security flags, PostgreSQL URL, WhiteNoise static files and environment secrets. A Render Blueprint is now prepared, but no deployment is launched; uploaded media needs durable storage. |
| Responsive UI and end-to-end browser flows | PARTIALLY COMPLETED | Responsive CSS breakpoints and rendered-view tests exist. Manual desktop/tablet/mobile browser walkthrough remains to be performed. |
| GitHub repository, live app, candidate screen recording | MISSING | No `.git` directory is present; Git and GitHub CLI are unavailable in this workspace. No hosting account/credentials or video recording are available. |
| REST API | MISSING | The application uses authenticated server-rendered Django views/forms; a REST API is not part of the current implementation. |

## Findings and changes in this audit

- Booking creation previously calculated duration from a possibly stale service instance before acquiring the database lock. It now reloads the service under lock and derives the end time and duration snapshot from that locked row.
- Rescheduling previously locked the booking before the provider row, opposite to booking creation/status updates, creating a lock inversion risk. It now uses provider-first locking and rechecks the booking status after acquiring locks.
- MySQL does not implement the project's conditional unique constraints for active payments/favourites (Django warning `models.W036`). Payment attempt creation and favourite toggles serialize on the booking/customer row. Booking interval conflicts have separate MySQL triggers, PostgreSQL exclusion constraint and SQLite provider write-lock strategy.
- Invalid payment verification no longer downgrades a previously succeeded payment, and refunded payments cannot be promoted back to succeeded by checkout verification or a captured webhook.
- Added a provider lock-version field, provider association for bookings, PostgreSQL GiST exclusion constraint, MySQL insert/update triggers, and SQLite write serialization. Existing booking rows were backfilled; PostgreSQL migration checks for overlapping legacy active bookings before installing its constraint.
- Expanded concurrency tests to cover exact and partial overlaps, adjacent intervals, separate slots, rejected/cancelled slot release, occupied reschedules, concurrent booking requests, and concurrent reschedules. MySQL 8.0.33 direct-insert protection and race tests pass; SQLite independent-connection races pass. PostgreSQL execution remains pending because no PostgreSQL server is configured here.
- Redesigned the administrator dashboard to match the attached purple-and-white reference, added mobile sidebar controls, actionable Django Admin links, paginated record tables, live search/filter controls, charts, payment period filters, and empty states.
- Added a distinct provider approval status and review timestamp. Migration `accounts.0005_providerprofile_approval_reviewed_at_and_more` maps existing verified providers to approved and other profiles to pending; approve/reject actions are POST-only, CSRF-protected, and require the provider-profile change permission. Rejection does not deactivate the account or services.

## Checks run

Run from PowerShell in the project directory:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings --verbosity=2
```

The final suite passed all 61 tests on MySQL 8.0.33 in 163.3 seconds. The race suite passed on MySQL, and its direct insert test confirmed the database trigger rejects an overlapping booking. The independent-connection create/reschedule races also passed on SQLite; the PostgreSQL-only database-constraint case is skipped when using SQLite. Django emitted three existing `models.W036` warnings for conditional unique indexes on payments and favourites. `manage.py check` passed, migrations applied through `bookings.0005`, and migration consistency reported no changes. PostgreSQL migrations could not be executed locally.

## Remaining work before submission

1. Run the PostgreSQL exclusion-constraint migration and direct-conflict test if PostgreSQL is the deployment database.
2. Configure and test Razorpay Test Mode with the candidate's own credentials; do not commit keys.
3. Complete manual desktop/tablet/mobile flows with customer, provider and administrator accounts.
4. Initialize Git, inspect staged files for secrets/media/build artifacts, push to the candidate's GitHub repository, deploy with managed PostgreSQL and durable media storage, then record a 5-10 minute demonstration.

## Final verification record

The entries below are historical runs. The latest progress update follows them.

- `manage.py check --settings=config.test_settings`: passed, no issues.
- `manage.py makemigrations --check --dry-run --settings=config.test_settings`: passed, no model changes needed.
- `manage.py migrate --noinput`: applied the additive provider-approval migration to the configured local database.
- `manage.py test --settings=config.test_settings --verbosity=2`: passed, 49 tests in 139.6 seconds. The run logs expected MySQL conditional-constraint warnings and deliberate email-failure logging from a test.
- `manage.py collectstatic --noinput --settings=config.test_settings`: passed; copied the dashboard stylesheet and one other new/changed asset, with 150 files unchanged.
- Focused rerun of the three administrator approval/dashboard tests after the INR-only payment aggregation change: passed (3 tests).
- Focused dashboard template-rendering test after the final HTML accessibility adjustment: passed (1 test).

## Latest progress update (17 October 2026)

- The current full suite passed all 76 tests on the configured MySQL test database using `manage.py test --keepdb --verbosity=1`.
- Django system check passed after preparing the Render deployment configuration.
- Production-settings smoke check passed for Render's generated hostname, HTTPS proxy header, and derived site URL.
- `render.yaml` and Render-aware configuration are prepared. No Git repository, GitHub remote, or live Render service exists yet; Git/GitHub and Render account connections are unavailable in this workspace.
- A timed, candidate-narrated recording plan is in `docs/SCREEN_RECORDING_SCRIPT.md`; no recording has been made.
- This is 11/15 checklist items complete, 2 partial, and 2 pending. Partial items are final browser review and GitHub publication (README is complete). Pending items are the live deployment and candidate recording. PostgreSQL concurrency migration/test execution remains a deployment gate.
