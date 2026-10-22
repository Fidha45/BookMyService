from datetime import date, datetime, timedelta
import uuid
import hashlib
import hmac
import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction
from config.views import forbidden_response
from services.models import Service
from .models import Booking, Notification, Payment
from .logic import available_slots, create_booking, report_booking_problem, reschedule_booking, transition

@login_required
def book(request, pk):
    service = get_object_or_404(Service, pk=pk, is_active=True, provider__user__is_active=True)
    if request.user.role != "customer":
        if request.method == "POST":
            return forbidden_response(request)
        if request.user.role == "provider":
            messages.info(request, "Bookings must be placed from a customer account. Sign in with a customer account to book this service.")
            return redirect("service_detail", pk=service.pk)
        return forbidden_response(request)
    default_day = timezone.localdate() + timedelta(days=1)
    selected_day = default_day
    request_key = str(uuid.uuid4())
    if request.method == "GET" and request.GET.get("date"):
        try: selected_day = date.fromisoformat(request.GET["date"])
        except ValueError: pass
    if request.method == "POST":
        try:
            start = datetime.fromisoformat(request.POST["start_at"])
            if timezone.is_naive(start): start = timezone.make_aware(start)
            else: start = start.astimezone(timezone.get_current_timezone())
            key = uuid.UUID(request.POST.get("request_key") or str(uuid.uuid4()))
            create_booking(request.user, service, start, request_key=key)
            messages.success(request, "Booking request sent to the provider.")
            return redirect("dashboard")
        except (ValidationError, ValueError, KeyError) as e:
            messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else "Enter a valid date and time.")
        try: selected_day = date.fromisoformat(request.POST.get("date", ""))
        except ValueError: pass
    slots = available_slots(service, selected_day)
    selected_start = request.GET.get("start_at", "") if request.method == "GET" else ""
    if not any(slot.strftime("%Y-%m-%dT%H:%M") == selected_start for slot in slots):
        selected_start = ""
    return render(request, "bookings/form.html", {"service": service, "selected_day": selected_day, "slots": slots, "request_key": request_key, "selected_start": selected_start})


def _customer_reschedule_booking(request, pk):
    if request.user.role != "customer":
        return forbidden_response(request)
    return get_object_or_404(
        Booking.objects.select_related("service", "service__category", "service__provider", "service__provider__user"),
        pk=pk,
        customer=request.user,
    )


def _reschedule_start(value):
    start = datetime.fromisoformat(value)
    if timezone.is_naive(start):
        return timezone.make_aware(start)
    return start.astimezone(timezone.get_current_timezone())


def _render_reschedule_form(request, booking, day=None, selected_start="", errors=None, status=200):
    day = day or timezone.localdate(booking.start_at)
    slots = available_slots(booking.service, day, exclude_booking_id=booking.pk)
    if selected_start and not any(slot.strftime("%Y-%m-%dT%H:%M") == selected_start for slot in slots):
        selected_start = ""
    return render(request, "bookings/reschedule.html", {
        "booking": booking,
        "selected_day": day,
        "minimum_day": timezone.localdate(),
        "slots": slots,
        "selected_start": selected_start,
        "errors": errors or [],
    }, status=status)


@login_required
def reschedule(request, pk):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])
    booking = _customer_reschedule_booking(request, pk)
    if isinstance(booking, HttpResponse):
        return booking
    if not booking.customer_can_reschedule:
        messages.error(request, "This booking can no longer be rescheduled.")
        return redirect("dashboard")

    if request.method == "GET":
        try:
            selected_day = date.fromisoformat(request.GET.get("date", "")) if request.GET.get("date") else timezone.localdate(booking.start_at)
        except ValueError:
            selected_day = timezone.localdate(booking.start_at)
        return _render_reschedule_form(request, booking, selected_day)

    errors = []
    raw_start = request.POST.get("start_at", "")
    try:
        start = _reschedule_start(raw_start)
        selected_day = timezone.localtime(start).date()
        open_slots = available_slots(booking.service, selected_day, exclude_booking_id=booking.pk)
        if start not in open_slots:
            raise ValidationError("That time is no longer available. Please choose another slot.")
        if request.POST.get("back"):
            return _render_reschedule_form(request, booking, selected_day, raw_start)
        if not request.POST.get("confirm"):
            return render(request, "bookings/reschedule.html", {
                "booking": booking,
                "confirmation": True,
                "new_start": start,
                "new_end": start + timedelta(minutes=booking.duration_at_booking),
                "new_start_value": timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"),
            })
        reschedule_booking(booking, start)
        messages.success(request, "Your appointment was rescheduled successfully.")
        return redirect("dashboard")
    except (ValidationError, ValueError, TypeError, OverflowError) as exc:
        errors = exc.messages if isinstance(exc, ValidationError) else ["Choose a valid date and time slot."]
        try:
            selected_day = date.fromisoformat(raw_start[:10])
        except ValueError:
            selected_day = timezone.localdate(booking.start_at)
        return _render_reschedule_form(request, booking, selected_day, errors=errors, status=400)


@login_required
def reschedule_slots(request, pk):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    booking = _customer_reschedule_booking(request, pk)
    if isinstance(booking, HttpResponse):
        return booking
    if not booking.customer_can_reschedule:
        return JsonResponse({"error": "This booking can no longer be rescheduled."}, status=409)
    try:
        selected_day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return JsonResponse({"error": "Choose a valid date."}, status=400)
    slots = available_slots(booking.service, selected_day, exclude_booking_id=booking.pk)
    return JsonResponse({"slots": [{"value": timezone.localtime(slot).strftime("%Y-%m-%dT%H:%M"), "label": timezone.localtime(slot).strftime("%I:%M %p").lstrip("0")} for slot in slots]})

@login_required
def booking_action(request, pk, action):
    booking = get_object_or_404(Booking.objects.select_related("service", "service__provider"), pk=pk)
    if request.method != "POST": return forbidden_response(request)
    return_to_detail = request.POST.get("return_to") == "detail"
    try:
        if action == "reschedule":
            if request.user != booking.customer or booking.status not in {"pending", "confirmed"}: raise ValidationError("This booking cannot be rescheduled.")
            start = timezone.make_aware(datetime.fromisoformat(request.POST["start_at"]))
            reschedule_booking(booking, start)
            messages.success(request, "Booking rescheduled.")
        elif action == "report_problem":
            reason = request.POST.get("reason", "").strip()
            desc = request.POST.get("description", "").strip()
            full_description = f"Reason: {reason}\n\n{desc}" if reason else desc
            report_booking_problem(booking.pk, request.user, full_description)
            messages.success(request, "Your problem report was sent to the administrator. Completion is paused until it is reviewed.")
        else:
            status_map = {
                "confirm": Booking.Status.CONFIRMED,
                "reject": Booking.Status.REJECTED,
                "start": Booking.Status.IN_PROGRESS,
                "complete": Booking.Status.AWAITING_CUSTOMER_CONFIRMATION,
                "confirm_completion": Booking.Status.COMPLETED,
                "cancel": Booking.Status.CANCELLED,
            }
            if action not in status_map: return forbidden_response(request)
            transition(booking, status_map[action], request.user)
            if action == "complete":
                messages.success(request, "Service marked as completed. Waiting for customer confirmation.")
            elif action == "confirm_completion":
                messages.success(request, "Work completion confirmed. You can now leave a review.")
            else:
                messages.success(request, "Booking updated.")
    except (ValidationError, ValueError, KeyError) as e:
        messages.error(request, "; ".join(e.messages) if hasattr(e, "messages") else "Enter a valid date and time.")
    return redirect("booking_detail", pk=booking.pk) if return_to_detail else redirect("dashboard")


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "service", "service__category", "service__provider", "service__provider__user")
        .prefetch_related("problem_reports", "payments"), pk=pk,
    )
    is_customer = booking.customer_id == request.user.pk
    is_provider = booking.service.provider.user_id == request.user.pk
    if not (request.user.is_staff or is_customer or is_provider):
        return forbidden_response(request)
    context = {
        "booking": booking,
        "is_booking_customer": is_customer,
        "is_booking_provider": is_provider,
        "open_problem_report": booking.open_problem_report,
        "latest_problem_report": booking.latest_problem_report,
        "latest_payment": booking.payments.order_by("-created_at", "-pk").first(),
    }
    if is_provider:
        context["pending_count"] = Booking.objects.filter(
            service__provider__user=request.user, status=Booking.Status.PENDING
        ).count()
        context["unread_notification_count"] = Notification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).count()
    if is_customer:
        context["active_nav"] = "bookings"
    return render(request, "bookings/detail.html", context)


@login_required
def notifications(request):
    rows = Notification.objects.filter(recipient=request.user).select_related("booking")
    return render(request, "bookings/notifications.html", {"notifications": rows})


@login_required
def notification_action(request, pk=None, action="read"):
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    qs = Notification.objects.filter(recipient=request.user, read_at__isnull=True)
    if action == "all": qs.update(read_at=timezone.now())
    elif action == "read" and pk: qs.filter(pk=pk).update(read_at=timezone.now())
    else: return forbidden_response(request)
    return redirect("notifications")


@login_required
def pay_booking(request, pk):
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    # Serialize checkout attempts per booking so concurrent requests reuse the
    # same active payment attempt.
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update().select_related("service", "service__provider__user"), pk=pk, customer=request.user)
        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            messages.error(request, "This booking is not eligible for payment."); return redirect("dashboard")
        payment = booking.payments.exclude(status=Payment.Status.FAILED).first()
        if payment and payment.status == Payment.Status.SUCCEEDED:
            return redirect("payment_confirmation", pk=payment.pk)
        if not payment:
            payment = Payment.objects.create(booking=booking, amount=booking.price_at_booking)
    try:
        gateway_ready = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
        if not gateway_ready:
            return render(request, "bookings/checkout.html", {
                "payment": payment,
                "key_id": "",
                "amount_paise": int(payment.amount * 100),
                "gateway_ready": False,
            })
        if not payment.gateway_order_id:
            from .payments import create_gateway_order
            payment = create_gateway_order(payment)
        return render(request, "bookings/checkout.html", {"payment": payment, "key_id": settings.RAZORPAY_KEY_ID, "amount_paise": int(payment.amount * 100), "gateway_ready": True})
    except (ValidationError, KeyError) as exc:
        if "payment" in locals() and payment.status != Payment.Status.SUCCEEDED and not payment.gateway_order_id:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
        if isinstance(exc, ValidationError): messages.error(request, "; ".join(exc.messages))
        else: messages.error(request, "The payment gateway did not return a valid order.")
        return redirect("dashboard")


@login_required
def verify_payment(request, pk):
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    payment = get_object_or_404(Payment.objects.select_related("booking"), pk=pk, booking__customer=request.user)
    try:
        from .payments import verify_checkout
        verify_checkout(payment, request.POST.get("razorpay_order_id", ""), request.POST.get("razorpay_payment_id", ""), request.POST.get("razorpay_signature", ""))
        messages.success(request, "Payment verified by the gateway.")
        return redirect("payment_confirmation", pk=payment.pk)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("dashboard")


@login_required
def payment_confirmation(request, pk):
    payment = get_object_or_404(
        Payment.objects.select_related(
            "booking__customer", "booking__service__provider__user", "booking__service__category"
        ),
        pk=pk,
        booking__customer=request.user,
        status=Payment.Status.SUCCEEDED,
    )
    booking = payment.booking
    return render(request, "bookings/confirmation.html", {"payment": payment, "booking": booking})


@login_required
def payment_failed(request, pk):
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    payment = get_object_or_404(Payment.objects.select_related("booking"), pk=pk, booking__customer=request.user)
    if payment.status not in (Payment.Status.SUCCEEDED, Payment.Status.REFUNDED):
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status", "updated_at"])
        from .notifications import notify_booking
        notify_booking(payment.booking, f"payment-failed-{payment.pk}", "The payment attempt did not complete. You can retry from your dashboard.", payment.booking.customer)
    messages.error(request, "Payment was not completed. You can retry from your dashboard.")
    return redirect("dashboard")


@login_required
def invoice(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("customer", "service__provider__user", "service__category").prefetch_related("payments"), pk=pk)
    if not (request.user.is_staff or request.user == booking.customer or request.user == booking.service.provider.user):
        return forbidden_response(request)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape
        import io
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=18*mm, bottomMargin=18*mm, title=f"Booking confirmation {booking.reference}")
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="BrandTitle", parent=styles["Title"], textColor=colors.HexColor("#6043ad"), alignment=TA_CENTER, spaceAfter=4*mm))
        styles.add(ParagraphStyle(name="SectionHeading", parent=styles["Heading2"], textColor=colors.HexColor("#352d4c"), spaceBefore=5*mm, spaceAfter=2*mm))
        para = lambda value: Paragraph(escape(str(value or "Not provided")), styles["BodyText"])
        provider = booking.service.provider
        customer_name = booking.customer.get_full_name() or booking.customer.email
        scheduled = timezone.localtime(booking.start_at).strftime("%A, %d %B %Y at %I:%M %p")
        created = timezone.localtime(booking.created_at).strftime("%d %b %Y, %I:%M %p")
        paid = booking.payments.filter(status=Payment.Status.SUCCEEDED).first()
        story = [Paragraph("BookMyService", styles["BrandTitle"]), Paragraph("Booking confirmation", styles["Heading1"]),
                 Paragraph(f"Reference: {escape(str(booking.reference))}", styles["BodyText"]), Spacer(1, 4*mm)]
        def detail_table(rows):
            table = Table([[para(label), para(value)] for label, value in rows], colWidths=[43*mm, 117*mm], hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f3f0f9")), ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#51466a")), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#e5e0ec")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 9), ("RIGHTPADDING", (0,0), (-1,-1), 9), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
            story.append(table)
        story.append(Paragraph("Booking details", styles["SectionHeading"]))
        detail_table([("Service", booking.service.name), ("Category", booking.service.category.name), ("Description", booking.service.description[:500]), ("Scheduled", scheduled), ("Status", booking.get_status_display()), ("Created", created)])
        story.append(Paragraph("Customer", styles["SectionHeading"]))
        detail_table([("Name", customer_name), ("Email", booking.customer.email), ("Phone", booking.customer.phone or "Not provided")])
        story.append(Paragraph("Service provider", styles["SectionHeading"]))
        detail_table([("Provider", provider.display_name), ("Location", provider.location), ("Email", provider.user.email), ("Phone", provider.user.phone or "Not provided")])
        story.append(Paragraph("Price and payment", styles["SectionHeading"]))
        detail_table([("Booking price", f"INR {booking.price_at_booking}"), ("Payment status", "Paid" if paid else "Unpaid"), ("Payment reference", paid.gateway_payment_id if paid else "Not provided")])
        story.extend([Spacer(1, 6*mm), Paragraph("The booking price reflects the amount saved when the booking was made. Any taxes or additional charges are shown only if included in that agreed price.", styles["BodyText"])])
        doc.build(story)
        response = HttpResponse(output.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="booking-confirmation-{booking.pk}.pdf"'
        return response
    except ImportError:
        return HttpResponse("Booking confirmation PDF dependency is not installed. Run: pip install reportlab", status=503)


@csrf_exempt
def razorpay_webhook(request):
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not secret: return JsonResponse({"error": "webhook not configured"}, status=503)
    expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature): return JsonResponse({"error": "invalid signature"}, status=400)
    try:
        event = json.loads(request.body)
        if event.get("event") not in {"payment.captured", "payment.failed"}: return JsonResponse({"status": "ignored"})
        entity = event["payload"]["payment"]["entity"]
        with transaction.atomic():
            payment = Payment.objects.select_for_update().select_related("booking", "booking__service__provider__user").get(gateway_order_id=entity["order_id"])
            from .notifications import notify_booking
            if event["event"] == "payment.failed":
                if payment.status not in (Payment.Status.SUCCEEDED, Payment.Status.REFUNDED):
                    payment.gateway_payment_id = entity.get("id")
                    payment.status = Payment.Status.FAILED
                    payment.save(update_fields=["gateway_payment_id", "status", "updated_at"])
                    notify_booking(payment.booking, f"payment-failed-{entity.get('id')}", "A payment attempt failed. You can retry from your dashboard.", payment.booking.customer)
            else:
                if entity.get("amount") != int(payment.amount * 100) or entity.get("currency") != payment.currency or entity.get("status") != "captured":
                    return JsonResponse({"error": "amount or status mismatch"}, status=400)
                if payment.status == Payment.Status.REFUNDED:
                    return JsonResponse({"error": "payment has already been refunded"}, status=409)
                if payment.status != Payment.Status.SUCCEEDED:
                    payment.gateway_payment_id = entity["id"]
                    payment.status = Payment.Status.SUCCEEDED
                    payment.verified_at = timezone.now()
                    payment.save(update_fields=["gateway_payment_id", "status", "verified_at", "updated_at"])
                    notify_booking(payment.booking, f"payment-{entity['id']}", "Payment confirmed for your booking.", payment.booking.customer)
                    notify_booking(payment.booking, f"payment-provider-{entity['id']}", "A customer payment was confirmed.", payment.booking.service.provider.user)
    except (ValueError, KeyError, TypeError, Payment.DoesNotExist):
        return JsonResponse({"error": "invalid event payload"}, status=400)
    return JsonResponse({"status": "ok"})
