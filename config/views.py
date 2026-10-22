from django.shortcuts import redirect, render


def admin_home(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard")
    return redirect("admin:login")

def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def forbidden_response(request):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)

