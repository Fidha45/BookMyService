(() => {
  const body = document.body;
  const sidebar = document.getElementById('customer-sidebar');
  const toggle = document.getElementById('customer-sidebar-toggle');
  const backdrop = document.querySelector('.customer-sidebar-backdrop');

  if (!sidebar || !toggle || !backdrop) return;

  const mobileQuery = window.matchMedia('(max-width: 767.98px)');
  let mobileOpen = false;

  function syncState() {
    if (mobileQuery.matches) {
      body.classList.toggle('customer-sidebar-mobile-open', mobileOpen);
      backdrop.hidden = !mobileOpen;
      sidebar.inert = !mobileOpen;
      sidebar.setAttribute('aria-hidden', String(!mobileOpen));
      toggle.setAttribute('aria-expanded', String(mobileOpen));
      toggle.setAttribute('aria-label', mobileOpen ? 'Close navigation menu' : 'Open navigation menu');
      body.style.overflow = mobileOpen ? 'hidden' : '';
    } else {
      mobileOpen = false;
      body.classList.remove('customer-sidebar-mobile-open');
      body.style.overflow = '';
      backdrop.hidden = true;
      const collapsed = body.classList.contains('customer-sidebar-collapsed');
      sidebar.inert = collapsed;
      sidebar.setAttribute('aria-hidden', String(collapsed));
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.setAttribute('aria-label', collapsed ? 'Open navigation sidebar' : 'Collapse navigation sidebar');
    }
  }

  function closeMobileMenu(returnFocus = false) {
    mobileOpen = false;
    syncState();
    if (returnFocus) toggle.focus();
  }

  toggle.addEventListener('click', () => {
    if (mobileQuery.matches) {
      mobileOpen = !mobileOpen;
      syncState();
      if (mobileOpen) sidebar.querySelector('a')?.focus();
      else toggle.focus();
      return;
    }

    body.classList.toggle('customer-sidebar-collapsed');
    syncState();
  });

  backdrop.addEventListener('click', () => closeMobileMenu(true));
  sidebar.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      if (mobileQuery.matches) closeMobileMenu();
    });
  });

  document.addEventListener('keydown', (event) => {
    const isOpen = mobileQuery.matches
      ? mobileOpen
      : !body.classList.contains('customer-sidebar-collapsed');

    if (event.key === 'Escape' && isOpen) {
      if (mobileQuery.matches) closeMobileMenu(true);
      else {
        body.classList.add('customer-sidebar-collapsed');
        syncState();
        toggle.focus();
      }
      return;
    }

    if (event.key !== 'Tab' || !mobileQuery.matches || !mobileOpen) return;
    const focusable = [...sidebar.querySelectorAll('a[href], button:not([disabled])')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  mobileQuery.addEventListener('change', () => {
    mobileOpen = false;
    syncState();
  });
  syncState();
})();
