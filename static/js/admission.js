/* ==========================================================================
   BALOCH BOYS HOSTEL — ADMISSION FORM JAVASCRIPT
   static/js/admission.js
   Handles: step navigation, per-field validation, progress bar,
            review generation, file list, privacy modal, submit guard.
   ========================================================================== */
(function () {
  'use strict';

  const form = document.getElementById('admissionForm');
  if (!form) return;

  const steps       = Array.from(form.querySelectorAll('.step'));
  const progressFill = document.getElementById('progressFill');
  const progressBar  = document.querySelector('.admission-progress');
  const stepLabels   = Array.from(document.querySelectorAll('.admission-progress__steps li'));
  const btnPrev     = document.getElementById('btnPrev');
  const btnNext     = document.getElementById('btnNext');
  const btnSubmit   = document.getElementById('btnSubmit');
  const reviewGrid  = document.getElementById('reviewGrid');

  const TOTAL = steps.length;
  let current = 1;

  /* ---------- Field-level validators ---------- */
  const validators = {
    full_name: v => v.trim().length >= 3 || 'Please enter the full name.',
    father_name: v => v.trim().length >= 3 || "Please enter father's name.",
    date_of_birth: v => {
      if (!v) return 'Please select a date of birth.';
      const d = new Date(v);
      if (isNaN(d.getTime())) return 'Invalid date.';
      const age = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24 * 365.25);
      if (age < 10) return 'Applicant must be at least 10 years old.';
      if (age > 80) return 'Please check the date of birth.';
      return true;
    },
    cnic: v => {
      if (!v) return 'Please enter CNIC or B-Form number.';
      const digits = v.replace(/[^0-9]/g, '');
      if (digits.length < 13) return 'CNIC must contain at least 13 digits.';
      return true;
    },
    phone: v => {
      if (!v) return 'Please enter a phone number.';
      const digits = v.replace(/[^0-9]/g, '');
      if (digits.length < 10 || digits.length > 15) return 'Enter a valid phone number.';
      return true;
    },
    whatsapp: v => {
      if (!v) return true; // optional
      const digits = v.replace(/[^0-9]/g, '');
      if (digits.length < 10 || digits.length > 15) return 'Enter a valid WhatsApp number.';
      return true;
    },
    institution_name: v => v.trim().length >= 2 || 'Please enter institution name.',
    class_degree: v => v.trim().length >= 1 || 'Please enter class or degree.',
    institution_location: v => v.trim().length >= 2 || 'Please enter institution location.',
    guardian_name: v => v.trim().length >= 3 || 'Please enter guardian name.',
    guardian_contact: v => {
      if (!v) return 'Please enter guardian contact number.';
      const digits = v.replace(/[^0-9]/g, '');
      if (digits.length < 10 || digits.length > 15) return 'Enter a valid contact number.';
      return true;
    },
    guardian_relationship: v => v.trim().length > 0 || 'Please select a relationship.',
    guardian_address: v => v.trim().length >= 5 || 'Please enter the address.',
    preferred_room: v => v.trim().length > 0 || 'Please select a room type.',
    expected_joining: v => v ? true : 'Please select a joining date.',
    monthly_budget: v => {
      if (!v) return true; // optional
      const n = Number(v);
      if (isNaN(n) || n < 0) return 'Enter a valid amount.';
      return true;
    },
    additional_requirements: () => true,
    privacy_accept: (v, el) => (el && el.checked) || 'You must accept the privacy statement.'
  };

  /* ---------- Helpers ---------- */
  const fieldWrapper = (el) => el.closest('.field') || el.closest('.privacy');
  const errorElFor = (name) => form.querySelector(`[data-error-for="${name}"]`);

  function setFieldState(el, valid, message) {
    const wrap = fieldWrapper(el);
    const err  = errorElFor(el.name);
    if (!wrap) return;
    wrap.classList.toggle('has-error', !valid);
    wrap.classList.toggle('is-valid', valid && el.type !== 'checkbox' && el.type !== 'file');
    if (err) err.textContent = valid ? '' : (message || '');
  }

  function validateField(el) {
    if (!el.name) return true;
    const fn = validators[el.name];
    if (!fn) return true;
    const result = fn(el.value, el);
    const ok = result === true;
    setFieldState(el, ok, ok ? '' : result);
    return ok;
  }

  function validateStep(stepIndex) {
    const step = steps[stepIndex - 1];
    if (!step) return true;
    let allValid = true;
    step.querySelectorAll('input, textarea, select').forEach((el) => {
      if (el.type === 'hidden' || el.disabled) return;
      if (!validateField(el)) allValid = false;
    });
    return allValid;
  }

  /* ---------- File upload preview ---------- */
  const fileInput = document.getElementById('documents');
  const fileList  = document.getElementById('fileList');
  const MAX_FILES = 3;
  const MAX_SIZE  = 5 * 1024 * 1024;

  function renderFileList() {
    if (!fileList || !fileInput) return;
    fileList.innerHTML = '';
    Array.from(fileInput.files).forEach((file, i) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${file.name} · ${(file.size/1024).toFixed(0)} KB</span>`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = '×';
      remove.setAttribute('aria-label', `Remove ${file.name}`);
      remove.addEventListener('click', () => removeFile(i));
      li.appendChild(remove);
      fileList.appendChild(li);
    });
  }

  function removeFile(index) {
    if (!fileInput) return;
    const dt = new DataTransfer();
    Array.from(fileInput.files).forEach((f, i) => { if (i !== index) dt.items.add(f); });
    fileInput.files = dt.files;
    renderFileList();
  }

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      const err = errorElFor('documents');
      if (fileInput.files.length > MAX_FILES) {
        if (err) err.textContent = `You can upload up to ${MAX_FILES} files.`;
        fileInput.value = '';
        renderFileList();
        return;
      }
      for (const f of fileInput.files) {
        if (f.size > MAX_SIZE) {
          if (err) err.textContent = `"${f.name}" exceeds the 5 MB limit.`;
          fileInput.value = '';
          renderFileList();
          return;
        }
      }
      if (err) err.textContent = '';
      renderFileList();
    });
  }

  /* ---------- Review builder ---------- */
  const REVIEW_FIELDS = [
    { group: 'Student Information', fields: [
      ['full_name', 'Full Name'],
      ['father_name', "Father's Name"],
      ['date_of_birth', 'Date of Birth'],
      ['cnic', 'CNIC / B-Form'],
      ['phone', 'Phone Number'],
      ['whatsapp', 'WhatsApp Number']
    ]},
    { group: 'Education', fields: [
      ['institution_name', 'Institution'],
      ['class_degree', 'Class / Degree'],
      ['institution_location', 'Institution Location']
    ]},
    { group: 'Guardian Details', fields: [
      ['guardian_name', 'Guardian Name'],
      ['guardian_contact', 'Contact Number'],
      ['guardian_relationship', 'Relationship'],
      ['guardian_address', 'Address']
    ]},
    { group: 'Accommodation', fields: [
      ['preferred_room', 'Preferred Room'],
      ['expected_joining', 'Expected Joining'],
      ['monthly_budget', 'Monthly Budget (PKR)'],
      ['additional_requirements', 'Additional Requirements']
    ]}
  ];

  function buildReview() {
    if (!reviewGrid) return;
    reviewGrid.innerHTML = '';
    REVIEW_FIELDS.forEach((section) => {
      const title = document.createElement('div');
      title.className = 'review__group-title';
      title.textContent = section.group;
      reviewGrid.appendChild(title);

      section.fields.forEach(([name, label]) => {
        const el = form.querySelector(`[name="${name}"]`);
        const value = el ? (el.value || '').trim() : '';
        if (!value) return; // skip empty optional fields
        const item = document.createElement('div');
        item.className = 'review__item';
        if (name === 'guardian_address' || name === 'additional_requirements') {
          item.classList.add('review__item--wide');
        }
        const lbl = document.createElement('span');
        lbl.className = 'review__label';
        lbl.textContent = label;
        const val = document.createElement('span');
        val.className = 'review__value';
        val.textContent = value;
        item.appendChild(lbl);
        item.appendChild(val);
        reviewGrid.appendChild(item);
      });
    });
  }

  /* ---------- Progress + navigation ---------- */
  function updateUI() {
    // Steps visibility
    steps.forEach((s, i) => s.classList.toggle('is-active', i === current - 1));

    // Progress bar
    if (progressFill) {
      progressFill.style.width = `${(current / TOTAL) * 100}%`;
    }
    if (progressBar) {
      progressBar.setAttribute('aria-valuenow', current);
    }

    // Step labels
    stepLabels.forEach((li, i) => {
      const n = i + 1;
      li.classList.toggle('is-active', n === current);
      li.classList.toggle('is-complete', n < current);
    });

    // Buttons
    if (btnPrev) btnPrev.hidden = current === 1;
    if (btnNext) btnNext.hidden = current === TOTAL;
    if (btnSubmit) btnSubmit.hidden = current !== TOTAL;

    // Focus the step title for screen readers
    const activeStep = steps[current - 1];
    const title = activeStep?.querySelector('.step__title');
    if (title) {
      title.setAttribute('tabindex', '-1');
      title.focus({ preventScroll: true });
    }

    // Scroll to top of form
    const formTop = form.getBoundingClientRect().top + window.scrollY - 100;
    window.scrollTo({ top: formTop, behavior: 'smooth' });
  }

  function goNext() {
    if (!validateStep(current)) return;
    if (current === TOTAL - 1) buildReview(); // entering step 5
    if (current < TOTAL) {
      current += 1;
      updateUI();
    }
  }

  function goPrev() {
    if (current > 1) {
      current -= 1;
      updateUI();
    }
  }

  if (btnNext)  btnNext.addEventListener('click', goNext);
  if (btnPrev)  btnPrev.addEventListener('click', goPrev);

  /* Enter key on inputs → advance */
  form.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'textarea') return;
    if (current < TOTAL) {
      e.preventDefault();
      goNext();
    }
  });

  /* Live validation on blur */
  form.querySelectorAll('input, textarea, select').forEach((el) => {
    if (el.type === 'hidden' || el.type === 'file') return;
    el.addEventListener('blur', () => validateField(el));
    el.addEventListener('input', () => {
      const wrap = fieldWrapper(el);
      if (wrap && wrap.classList.contains('has-error')) validateField(el);
    });
  });

  /* ---------- Privacy modal ---------- */
  const privacyModal = document.getElementById('privacyModal');
  const privacyClose = document.getElementById('privacyClose');
  const privacyOk    = document.getElementById('privacyOk');
  const openPrivacy  = form.querySelector('[data-open-privacy]');

  const showModal = (show) => {
    if (!privacyModal) return;
    privacyModal.hidden = !show;
    document.body.style.overflow = show ? 'hidden' : '';
    if (show) privacyClose?.focus();
  };

  openPrivacy?.addEventListener('click', (e) => { e.preventDefault(); showModal(true); });
  privacyClose?.addEventListener('click', () => showModal(false));
  privacyOk?.addEventListener('click', () => showModal(false));
  privacyModal?.addEventListener('click', (e) => { if (e.target === privacyModal) showModal(false); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && privacyModal && !privacyModal.hidden) showModal(false);
  });

  /* ---------- Submit guard ---------- */
  form.addEventListener('submit', (e) => {
    // Validate every step before allowing submission
    let allValid = true;
    for (let i = 1; i <= TOTAL - 1; i++) {
      if (!validateStep(i)) { allValid = false; break; }
    }
    const privacyEl = form.querySelector('[name="privacy_accept"]');
    if (privacyEl && !validateField(privacyEl)) allValid = false;

    if (!allValid) {
      e.preventDefault();
      // Find first invalid step and jump to it
      for (let i = 1; i <= TOTAL; i++) {
        if (!validateStep(i)) { current = i; updateUI(); break; }
      }
      return;
    }

    // Show loading state
    if (btnSubmit) {
      btnSubmit.classList.add('is-loading');
      btnSubmit.textContent = 'Submitting…';
      btnSubmit.disabled = true;
    }
  });

  /* ---------- Init ---------- */
  updateUI();
})();