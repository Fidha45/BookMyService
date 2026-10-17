from django.contrib.auth import logout

class ActiveUserMiddleware:
    """Expire authenticated sessions as soon as an account is deactivated."""
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if getattr(request, "user", None) is not None and request.user.is_authenticated and not request.user.is_active:
            logout(request)
        return self.get_response(request)
