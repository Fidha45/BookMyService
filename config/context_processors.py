def notification_count(request):
    context = {
        "unread_notification_count": 0,
        "pending_approval_count": 0,
        "open_reports_count": 0,
    }
    if request.user.is_authenticated:
        from bookings.models import Notification
        context["unread_notification_count"] = Notification.objects.filter(
            recipient=request.user, read_at__isnull=True,
        ).count()

        if request.path.startswith("/admin/") and request.user.is_staff:
            from accounts.models import ProviderProfile
            from bookings.models import ProblemReport

            context["pending_approval_count"] = ProviderProfile.objects.filter(
                approval_status=ProviderProfile.ApprovalStatus.PENDING,
            ).count()
            context["open_reports_count"] = ProblemReport.objects.filter(
                status=ProblemReport.Status.OPEN,
            ).count()
    return context
