from django import template
from django.templatetags.static import static

register = template.Library()


SERVICE_ARTWORK = {
    "ac-service": "Ac repair.jpg",
    "ac-repair": "Ac repair.jpg",
    "appliance-repair": "Appliance repair.jpg",
    "carpentry": "Carpentry.jpg",
    "electrical": "Electrical work.jpg",
    "electrical-work": "Electrical work.jpg",
    "home-renovation": "Home renovation.jpg",
    "house-cleaning": "House cleaning.jpg",
    "home-cleaning": "House cleaning.jpg",
    "painting": "Painting.jpg",
    "pest-control": "pest control.jpg",
    "plumbing": "plumbing.png",
}


@register.filter
def catalog_service_image(service):
    """Return the matching existing catalog photo for a service, if available."""
    category = getattr(service, "category", None)
    slug = getattr(category, "slug", "")
    filename = SERVICE_ARTWORK.get(str(slug).lower().replace("_", "-"))
    return static(f"images/services/{filename}") if filename else ""
