/* ==========================================================================
   BALOCH BOYS HOSTEL — GALLERY PAGE JAVASCRIPT
   static/js/gallery.js
   Handles: image lightbox (keyboard + buttons), category filtering.
   ========================================================================== */
(function () {
  'use strict';

  const grid = document.getElementById('galleryGrid');
  if (!grid) return; // Not on gallery page (or no images)

  /* ---------- 1. Category filtering ---------- */
  const filters = document.querySelectorAll('.gallery-filter');
  const items = Array.from(grid.querySelectorAll('.gallery-item'));

  filters.forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.filter;
      filters.forEach(b => {
        b.classList.toggle('is-active', b === btn);
        b.setAttribute('aria-selected', String(b === btn));
      });
      items.forEach((item) => {
        const cat = item.dataset.category || 'all';
        const show = target === 'all' || cat === target;
        item.style.display = show ? '' : 'none';
      });
    });
  });

  /* ---------- 2. Lightbox ---------- */
  const lb       = document.getElementById('lightbox');
  const lbImg    = document.getElementById('lbImg');
  const lbCap    = document.getElementById('lbCaption');
  const lbClose  = document.getElementById('lbClose');
  const lbPrev   = document.getElementById('lbPrev');
  const lbNext   = document.getElementById('lbNext');
  if (!lb || !lbImg) return;

  let currentIndex = 0;
  let visibleItems = [];

  const refreshVisible = () => {
    visibleItems = items.filter(i => i.style.display !== 'none');
  };

  const open = (index) => {
    refreshVisible();
    if (!visibleItems.length) return;
    currentIndex = Math.max(0, Math.min(index, visibleItems.length - 1));
    render();
    lb.hidden = false;
    lb.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    lbClose.focus();
  };

  const close = () => {
    lb.classList.remove('is-open');
    lb.hidden = true;
    document.body.style.overflow = '';
  };

  const render = () => {
    const item = visibleItems[currentIndex];
    if (!item) return;
    const img = item.querySelector('img');
    lbImg.src = item.dataset.src || (img ? img.src : '');
    lbImg.alt = item.dataset.caption || (img ? img.alt : '');
    lbCap.textContent = item.dataset.caption || '';
  };

  const prev = () => {
    currentIndex = (currentIndex - 1 + visibleItems.length) % visibleItems.length;
    render();
  };
  const next = () => {
    currentIndex = (currentIndex + 1) % visibleItems.length;
    render();
  };

  /* Click handlers */
  items.forEach((item) => {
    item.addEventListener('click', () => {
      refreshVisible();
      open(visibleItems.indexOf(item));
    });
  });

  lbClose.addEventListener('click', close);
  lbPrev.addEventListener('click', prev);
  lbNext.addEventListener('click', next);

  lb.addEventListener('click', (e) => {
    if (e.target === lb) close();
  });

  document.addEventListener('keydown', (e) => {
    if (!lb.classList.contains('is-open')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowLeft')  prev();
    else if (e.key === 'ArrowRight') next();
  });

  /* Focus trap (light) */
  lb.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const focusable = [lbClose, lbPrev, lbNext];
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });
})();