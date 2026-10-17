from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from bookings.models import Booking
from .forms import ReviewForm

@login_required
def review_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk, customer=request.user, status=Booking.Status.COMPLETED)
    if hasattr(booking, "review"):
        messages.info(request, "This booking already has a review."); return redirect("dashboard")
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        review = form.save(commit=False); review.booking = booking; review.customer = request.user
        review.save(); messages.success(request, "Thanks for your review."); return redirect("dashboard")
    return render(request, "form_page.html", {"form": form, "title": "Review completed service"})
