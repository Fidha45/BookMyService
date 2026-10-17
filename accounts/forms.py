from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator
from django.utils import timezone
from .models import User, ProviderProfile, AvailabilityBlock
from config.uploads import validate_image_upload

class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, validators=[RegexValidator(r"^[+()0-9 .-]{7,20}$", "Enter a valid phone number.")])
    role = forms.ChoiceField(
        choices=[(User.Role.CUSTOMER, "Customer"), (User.Role.PROVIDER, "Service provider")],
        widget=forms.RadioSelect,
        initial=User.Role.CUSTOMER,
    )
    class Meta:
        model = User
        fields = ("first_name", "email", "phone", "role")
    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists(): raise forms.ValidationError("An account with this email already exists.")
        return email
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = self.cleaned_data["role"]
        if commit: user.save()
        return user

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")

class ProviderProfileForm(forms.ModelForm):
    class Meta:
        model = ProviderProfile
        fields = ("display_name", "description", "location", "experience_years", "image")
    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))

class AvailabilityForm(forms.Form):
    start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type":"time"}))
    end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={"type":"time"}))
    def clean(self):
        data = super().clean()
        start, end = data.get("start_time"), data.get("end_time")
        if bool(start) != bool(end): raise forms.ValidationError("Enter both times or leave the day unavailable.")
        if start and start >= end: raise forms.ValidationError("Start time must be before end time.")
        return data

class AvailabilityBlockForm(forms.ModelForm):
    start_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    end_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    class Meta:
        model = AvailabilityBlock
        fields = ("start_at", "end_at", "reason")
    def clean(self):
        data = super().clean()
        if data.get("start_at") and data["start_at"] <= timezone.now():
            raise forms.ValidationError("A blocked period must start in the future.")
        if data.get("start_at") and data.get("end_at") and data["start_at"] >= data["end_at"]:
            raise forms.ValidationError("End time must be after start time.")
        return data
