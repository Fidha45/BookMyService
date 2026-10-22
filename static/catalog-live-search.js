(() => {
  const forms = document.querySelectorAll("form[data-live-search]");

  forms.forEach((form) => {
    const searchInput = form.querySelector('input[name="q"]');
    const resultsSelector = form.dataset.resultsSelector;
    const countSelector = form.dataset.countSelector;
    const paginationSelector = form.dataset.paginationSelector;
    if (!searchInput || !resultsSelector || !countSelector) return;

    let debounceTimer;
    let activeRequest;

    const updateResults = async () => {
      const params = new URLSearchParams();
      new FormData(form).forEach((value, key) => params.append(key, value));
      params.delete("page");

      const url = new URL(form.action, window.location.href);
      url.search = params.toString();
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;

      activeRequest?.abort();
      const request = new AbortController();
      activeRequest = request;
      const results = document.querySelector(resultsSelector);
      results?.setAttribute("aria-busy", "true");

      try {
        const response = await fetch(url.pathname + url.search, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: request.signal,
        });
        if (!response.ok) throw new Error(`Search request failed (${response.status})`);

        const responseHtml = await response.text();
        const parsedDocument = new DOMParser().parseFromString(responseHtml, "text/html");
        const nextResults = parsedDocument.querySelector(resultsSelector);
        const nextCount = parsedDocument.querySelector(countSelector);
        const currentCount = document.querySelector(countSelector);
        if (!results || !nextResults || !nextCount || !currentCount) return;

        results.replaceWith(nextResults);
        currentCount.textContent = nextCount.textContent;

        if (paginationSelector) {
          const currentPagination = document.querySelector(paginationSelector);
          const nextPagination = parsedDocument.querySelector(paginationSelector);
          if (currentPagination && nextPagination) currentPagination.replaceWith(nextPagination);
          else if (currentPagination) currentPagination.remove();
          else if (nextPagination) nextResults.insertAdjacentElement("afterend", nextPagination);
        }

        window.history.replaceState({}, "", url.pathname + url.search + url.hash);
      } catch (error) {
        if (error.name !== "AbortError") console.error("Could not update service search results.", error);
      } finally {
        if (activeRequest === request) {
          document.querySelector(resultsSelector)?.removeAttribute("aria-busy");
          activeRequest = undefined;
        }
      }
    };

    const scheduleUpdate = () => {
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(updateResults, 350);
    };

    searchInput.addEventListener("input", (event) => {
      if (!event.isComposing) scheduleUpdate();
    });
    searchInput.addEventListener("compositionend", scheduleUpdate);
  });
})();
