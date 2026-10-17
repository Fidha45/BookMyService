from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Avg, Q
from accounts.models import ProviderProfile
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    class Meta:
        verbose_name = "category"
        verbose_name_plural = "categories"
    def __str__(self): return self.name

class Service(models.Model):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.PROTECT, related_name="services")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="services")
    name = models.CharField(max_length=120)
    description = models.TextField()
    location = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=9, decimal_places=2, validators=[MinValueValidator(0)])
    duration_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    image = models.ImageField(upload_to="services/", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    @property
    def average_rating(self): return self.bookings.aggregate(value=Avg("review__rating"))["value"]
    def __str__(self): return self.name


class Favourite(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favourites")
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE, related_name="favourited_by")
    provider = models.ForeignKey(ProviderProfile, null=True, blank=True, on_delete=models.CASCADE, related_name="favourited_by")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=(Q(service__isnull=False, provider__isnull=True) | Q(service__isnull=True, provider__isnull=False)), name="favourite_has_one_target"),
            # MySQL unique indexes allow multiple NULL values, so these
            # unconditional constraints enforce uniqueness for whichever
            # target is populated while allowing the other target to be NULL.
            models.UniqueConstraint(fields=["customer", "service"], name="unique_customer_favourite_service"),
            models.UniqueConstraint(fields=["customer", "provider"], name="unique_customer_favourite_provider"),
        ]
