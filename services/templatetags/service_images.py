from django import template
from django.templatetags.static import static
from django.utils.text import slugify

register = template.Library()


SERVICE_ARTWORK = {
    "auto-care": "Car service.png",
    "auto-repair": "Car service.png",
    "automotive": "Car service.png",
    "car-service": "Car service.png",
    "car-services": "Car service.png",
    "ac-service": "Ac repair.jpg",
    "ac-repair": "Ac repair.jpg",
    "appliance-repair": "Appliance repair.jpg",
    "carpentry": "Carpentry.jpg",
    "electrical": "Electrical work.jpg",
    "electrical-work": "Electrical work.jpg",
    "home-renovation": "Home renovation.jpg",
    "house-cleaning": "House cleaning.jpg",
    "home-cleaning": "House cleaning.jpg",
    "laptop-repair": "Laptop repair.png",
    "laptop-computer-repair": "Laptop repair.png",
    "laptop-and-computer-repair": "Laptop repair.png",
    "computer-repair": "Laptop repair.png",
    "painting": "Painting.jpg",
    "photography": "Portrait photography.png",
    "portrait-photography": "Portrait photography.png",
    "pest-control": "pest control.jpg",
    "plumbing": "Plumbing service.png",
    "plumbing-service": "Plumbing service.png",
    "plumbing-visit": "Plumbing service.png",
    "preview-plumbing": "Plumbing service.png",
    "web-development": "Website development.png",
    "web-design": "Website development.png",
    "website-development": "Website development.png",
    "website-development-consultation": "Website development.png",
    "website-design": "Website development.png",
}


@register.filter
def catalog_service_image(service):
    """Return the matching existing catalog photo for a service, if available."""
    category = getattr(service, "category", None)
    candidates = (
        getattr(category, "slug", ""),
        getattr(category, "name", ""),
        getattr(service, "name", ""),
    )
    filename = next(
        (SERVICE_ARTWORK[key] for value in candidates if (key := slugify(value)) in SERVICE_ARTWORK),
        None,
    )
    return static(f"images/services/{filename}") if filename else ""
