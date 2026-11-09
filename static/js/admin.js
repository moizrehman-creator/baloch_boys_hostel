/* ==========================================================================
   BALOCH BOYS HOSTEL — ADMIN JAVASCRIPT
   static/js/admin.js
   Handles: sidebar toggle, table search, status change confirm,
            auto-dismiss flashes.
   ========================================================================== */
(function () {
  'use strict';

    /* ---------- Sidebar toggle ---------- */
  const toggle = document.getElementById('adminMenuToggle');
  const sidebar = document.getElementById('adminSidebar');
  
  if (toggle && sidebar) {
    // Overlay create karein
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);

    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('is-open');
      overlay.classList.toggle('is-active');
    });

    overlay.addEventListener('click', () => {
      sidebar.classList.remove('is-open');
      overlay.classList.remove('is-active');
    });
  }

  /* ---------- Table search (client-side) ---------- */
  const search = document.querySelector('.admin-search');
  const table = document.querySelector('.admin-table');
  if (search && table) {
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    search.addEventListener('input', () => {
      const q = search.value.trim().toLowerCase();
      rows.forEach((row) => {
        row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  /* ---------- Confirm destructive actions ---------- */
  document.querySelectorAll('[data-confirm]').forEach((el) => {
    el.addEventListener('click', (e) => {
      if (!confirm(el.dataset.confirm)) e.preventDefault();
    });
  });

  /* ---------- Auto-dismiss flash messages ---------- */
  setTimeout(() => {
    document.querySelectorAll('.admin-flash').forEach((f) => {
      f.style.transition = 'opacity .4s';
      f.style.opacity = '0';
      setTimeout(() => f.remove(), 420);
    });
  }, 6000);
})();