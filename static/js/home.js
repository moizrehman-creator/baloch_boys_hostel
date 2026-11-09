/* ==========================================================================
   BALOCH BOYS HOSTEL — HOMEPAGE JAVASCRIPT
   static/js/home.js
   Handles: 3D tilt cards, facility cursor glow, hero parallax,
            masonry lightbox (progressive enhancement over plain links).
   ========================================================================== */
(function () {
  'use strict';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 1. 3D tilt cards ---------- */
  if (!reduceMotion) {
    document.querySelectorAll('[data-tilt]').forEach((card) => {
      const inner = card.querySelector('.tilt-card__inner') || card;
      const MAX = 9;
      card.addEventListener('pointermove', (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        const rx = (py - 0.5) * -2 * MAX;
        const ry = (px - 0.5) *  2 * MAX;
        inner.style.transform =
          `perspective(1200px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg)`;
      });
      card.addEventListener('pointerleave', () => {
        inner.style.transform = 'perspective(1200px) rotateX(0) rotateY(0)';
      });
    });
  }

  /* ---------- 2. Facility card cursor glow ---------- */
  if (!reduceMotion) {
    document.querySelectorAll('.facility-card').forEach((card) => {
      card.addEventListener('pointermove', (e) => {
        const r = card.getBoundingClientRect();
        card.style.setProperty('--mx', `${e.clientX - r.left}px`);
        card.style.setProperty('--my', `${e.clientY - r.top}px`);
      });
    });
  }

  /* ---------- 3. Hero parallax (subtle) ---------- */
  if (!reduceMotion) {
    const heroBg = document.querySelector('.hero__bg-layer');
    if (heroBg) {
      let ticking = false;
      window.addEventListener('scroll', () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
          const y = window.scrollY;
          if (y < window.innerHeight) {
            heroBg.style.transform = `scale(1.08) translate3d(0, ${y * 0.15}px, 0)`;
          }
          ticking = false;
        });
      }, { passive: true });
    }
  }

  /* ---------- 4. Gallery lightbox (progressive) ----------
     Homepage links are already plain <a href="image">. If a lightbox
     library (e.g., GLightbox) is loaded later, hook it here. Otherwise
     the browser opens the image — no broken behavior either way.        */
  document.querySelectorAll('[data-lightbox]').forEach((link) => {
    link.addEventListener('click', (e) => {
      // If a global lightbox API is available, delegate to it.
      if (window.GLightbox) return; // let GLightbox handle
      // Graceful fallback: open in new tab
      e.preventDefault();
      window.open(link.href, '_blank', 'noopener');
    });
  });
})();