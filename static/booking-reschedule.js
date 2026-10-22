(() => {
  const form = document.querySelector('.booking-reschedule-form[data-slots-url]');
  if (!form) return;

  const dateInput = form.querySelector('input[type="date"]');
  const slotSelect = form.querySelector('select[name="start_at"]');
  const reviewButton = form.querySelector('[data-review-button]');
  const loading = form.querySelector('.booking-reschedule-loading');
  const csrf = form.querySelector('[name="csrfmiddlewaretoken"]')?.value;
  let activeRequest;

  function showError(message) {
    let error = form.querySelector('.booking-reschedule-errors');
    if (!error) {
      error = document.createElement('div');
      error.className = 'booking-reschedule-errors';
      error.setAttribute('role', 'alert');
      form.insertBefore(error, form.firstElementChild);
    }
    error.textContent = message;
  }

  function clearError() {
    form.querySelector('.booking-reschedule-errors')?.remove();
  }

  dateInput.addEventListener('change', async () => {
    clearError();
    if (!dateInput.value) return;

    activeRequest?.abort();
    activeRequest = new AbortController();
    slotSelect.disabled = true;
    reviewButton.disabled = true;
    loading.hidden = false;
    slotSelect.replaceChildren(new Option('Loading available times…', ''));

    try {
      const url = new URL(form.dataset.slotsUrl, window.location.origin);
      url.searchParams.set('date', dateInput.value);
      const response = await fetch(url, {
        headers: { 'Accept': 'application/json', 'X-CSRFToken': csrf || '' },
        credentials: 'same-origin',
        signal: activeRequest.signal,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not load available times. Try another date.');

      slotSelect.replaceChildren(new Option(result.slots.length ? 'Choose an available time' : 'No available times on this date', ''));
      result.slots.forEach((slot) => slotSelect.add(new Option(slot.label, slot.value)));
      slotSelect.disabled = result.slots.length === 0;
      reviewButton.disabled = result.slots.length === 0;
    } catch (error) {
      if (error.name !== 'AbortError') {
        slotSelect.replaceChildren(new Option('Unable to load available times', ''));
        showError(error.message || 'Could not load available times. Try another date.');
      }
    } finally {
      if (!activeRequest.signal.aborted) {
        loading.hidden = true;
        if (!slotSelect.options.length || slotSelect.options.length > 1) slotSelect.disabled = false;
        reviewButton.disabled = slotSelect.options.length <= 1;
      }
    }
  });
})();
