from django import forms
from .models import Service
from config.uploads import validate_image_upload
class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ("category", "name", "description", "location", "price", "duration_minutes", "image", "is_active")
    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get("image"))
