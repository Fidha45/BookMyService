# BookMyService assessment recording plan

Target length: about 7 minutes. Record the real application in a browser, use your own voice, and explain the decisions in your own words. Do not show `.env`, real passwords, payment secrets, or private customer data.

## Before recording

- Use a clean demo database with a customer, two providers, categories, services, and one scheduled booking.
- Open a private browser window and sign in only with demo accounts.
- Keep a second customer session ready to demonstrate the same-slot conflict.
- Confirm that the deployed demo contains no real personal information.

## Timed walkthrough

**0:00–0:35 — Introduction**

Name the project and explain that customers find/book local services, providers manage schedules and requests, and administrators manage marketplace records.

**0:35–1:20 — Customer discovery**

Show the service catalogue, category/search filters, and a service detail page with provider profile, price, duration, rating, and availability.

**1:20–2:20 — Booking and conflict protection**

Choose an available date and time and submit a booking. In the second customer session, try to request the same provider/time and show that the conflicting request is rejected. Explain that booking writes use a provider lock and the configured database guard.

**2:20–3:10 — Provider workflow**

Show provider availability and booking requests. Accept a request, move it through in-progress, then complete a separate demo booking. Point out that status transitions are checked on the server.

**3:10–4:00 — Customer booking management**

Return to the customer account. Show booking history/details, reschedule or cancel an eligible booking, and open the PDF confirmation. If a completed booking is present, submit a review.

**4:00–5:00 — Provider tools**

Show service editing and the earnings dashboard. Explain that earnings are estimates based on completed booking values and are not payout calculations.

**5:00–6:20 — Administrator tools**

Show live dashboard totals, provider approval, booking/user controls, then open the separate Services and Categories management pages in Django Admin.

**6:20–7:00 — Wrap-up**

Mention automated test coverage, the database used by the deployment, and any limitations that remain, including gateway credentials or PostgreSQL validation if those were not tested live.
