from django.urls import path
from .views import review_booking
urlpatterns = [path("booking/<int:pk>/", review_booking, name="review_booking")]
