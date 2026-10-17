from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models

class UserManager(BaseUserManager):
    use_in_migrations = True
    def create_user(self, email, password=None, **extra_fields):
        if not email: raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have is_staff=True and is_superuser=True.")
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        PROVIDER = "provider", "Service provider"
        ADMIN = "admin", "Administrator"
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=20, validators=[RegexValidator(r"^[+()0-9 .-]{7,20}$", "Enter a valid phone number.")])
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

class ProviderProfile(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="provider_profile")
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=120)
    experience_years = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to="providers/", blank=True)
    is_verified = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=12, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    approval_reviewed_at = models.DateTimeField(null=True, blank=True)
    # SQLite has no row-level SELECT FOR UPDATE. Incrementing this stable row
    # inside the booking transaction acquires SQLite's write lock before checks.
    booking_lock_version = models.PositiveBigIntegerField(default=0, editable=False)
    def __str__(self): return self.display_name

class WeeklyAvailability(models.Model):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="availability")
    weekday = models.PositiveSmallIntegerField(choices=[(i, name) for i, name in enumerate(("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"))])
    start_time = models.TimeField()
    end_time = models.TimeField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "weekday"], name="one_weekly_schedule_per_day"), models.CheckConstraint(condition=models.Q(start_time__lt=models.F("end_time")), name="availability_start_before_end")]

class AvailabilityBlock(models.Model):
    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="blocked_periods")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["start_at"]
        constraints = [models.CheckConstraint(condition=models.Q(start_at__lt=models.F("end_at")), name="block_start_before_end")]
