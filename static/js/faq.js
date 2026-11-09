/* ==========================================================================
   BALOCH BOYS HOSTEL — FAQ ACCORDION
   static/js/faq.js
   Progressive enhancement over native <details>.
   Without JS, all items still open/close natively.
   ========================================================================== */
(function () {
  'use strict';

  const container = document.getElementById('faqAccordion');
  if (!container) return;

  const items = Array.from(container.querySelectorAll('details.faq-entry'));

  items.forEach((item) => {
    item.addEventListener('toggle', () => {
      // When one opens, close the rest (accordion behavior)
      if (item.open) {
        items.forEach((other) => {
          if (other !== item && other.open) other.open = false;
        });
      }
    });
  });

  // Optional: smooth scroll to top of opened FAQ on small screens
  container.addEventListener('click', (e) => {
    const summary = e.target.closest('summary');
    if (!summary) return;
    if (window.innerWidth > 640) return;
    // Let the browser open/close, then scroll the item into view
    requestAnimationFrame(() => {
      const opened = summary.parentElement;
      if (opened.open) {
        const top = opened.getBoundingClientRect().top + window.scrollY - 90;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });
})();