from PIL import Image, UnidentifiedImageError
from django import forms

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024

def validate_image_upload(image):
    if not image:
        return image
    if image.size > MAX_IMAGE_SIZE:
        raise forms.ValidationError("Upload an image up to 5 MB.")
    try:
        image.seek(0)
        with Image.open(image) as uploaded:
            if uploaded.format not in ALLOWED_FORMATS:
                raise forms.ValidationError("Upload a JPG, PNG or WebP image.")
            uploaded.verify()
        image.seek(0)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise forms.ValidationError("The uploaded file is not a valid image.") from exc
    return image
