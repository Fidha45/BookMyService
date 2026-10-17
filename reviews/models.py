from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from bookings.models import Booking

class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="review")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=1500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.booking_id:
            booking = Booking.objects.filter(pk=self.booking_id).first()
            if booking is None:
                raise ValidationError({"booking": "The selected booking does not exist."})
            if booking.status != Booking.Status.COMPLETED:
                raise ValidationError({"booking": "Only completed bookings can be reviewed."})
            if self.customer_id != booking.customer_id:
                raise ValidationError({"customer": "Only the customer who booked may review."})
    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
