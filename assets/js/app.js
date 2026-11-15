(() => {
  'use strict';
  const toast = (message) => {
    const element = document.querySelector('.toast');
    if (!element) return;
    element.textContent = message;
    element.hidden = false;
    clearTimeout(element.dismissTimer);
    element.dismissTimer = setTimeout(() => { element.hidden = true; }, 3500);
  };
  const mobile = window.matchMedia('(max-width: 760px)');
  const toggle = document.querySelector('[data-sidebar-toggle]');
  const syncSidebar = () => {
    if (!toggle) return;
    const expanded = mobile.matches ? document.body.classList.contains('sidebar-open') : !document.body.classList.contains('sidebar-collapsed');
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.setAttribute('aria-label', expanded ? 'Згорнути бічне меню' : 'Відкрити бічне меню');
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.inert = mobile.matches && !expanded;
  };
  try { if (localStorage.getItem('studhub-sidebar') === 'collapsed') document.body.classList.add('sidebar-collapsed'); } catch (_) { /* Storage can be unavailable. */ }
  syncSidebar();
  mobile.addEventListener('change', syncSidebar);
  toggle?.addEventListener('click', () => {
    if (mobile.matches) document.body.classList.toggle('sidebar-open');
    else {
      document.body.classList.toggle('sidebar-collapsed');
      try { localStorage.setItem('studhub-sidebar', document.body.classList.contains('sidebar-collapsed') ? 'collapsed' : 'expanded'); } catch (_) { /* Optional preference. */ }
    }
    syncSidebar();
  });
  const closeSidebar = () => { document.querySelector('#profile-menu:popover-open')?.hidePopover(); document.body.classList.remove('sidebar-open'); syncSidebar(); toggle?.focus(); };
  document.querySelector('[data-sidebar-close]')?.addEventListener('click', closeSidebar);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !document.querySelector('#profile-menu:popover-open') && document.body.classList.contains('sidebar-open')) closeSidebar(); });
  document.querySelectorAll('[data-autosubmit]').forEach((input) => input.addEventListener('change', () => input.form?.requestSubmit()));
  document.querySelectorAll('[data-disclosure]').forEach((button) => {
    const panel = document.getElementById(button.dataset.disclosure);
    if (!panel) return;
    button.setAttribute('aria-expanded', String(!panel.hidden));
    button.addEventListener('click', () => { panel.hidden = !panel.hidden; button.setAttribute('aria-expanded', String(!panel.hidden)); });
  });
  document.querySelectorAll('[data-dialog]').forEach((button) => button.addEventListener('click', () => document.getElementById(button.dataset.dialog)?.showModal()));
  document.querySelectorAll('[data-dialog-close]').forEach((button) => button.addEventListener('click', () => button.closest('dialog')?.close()));
  document.querySelectorAll('dialog').forEach((dialog) => dialog.addEventListener('click', (event) => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  }));
  document.querySelectorAll('[data-copy]').forEach((button) => button.addEventListener('click', async () => {
    const input = document.getElementById(button.dataset.copy);
    if (!input) return;
    try { await navigator.clipboard.writeText(input.value); toast('Посилання скопійовано'); }
    catch (_) { input.focus(); input.select(); if (document.execCommand('copy')) toast('Посилання скопійовано'); else toast('Виділіть та скопіюйте посилання'); }
  }));
  document.querySelectorAll('[data-dismiss]').forEach((button) => button.addEventListener('click', () => button.parentElement.remove()));
  document.querySelectorAll('[data-avatar-preview]').forEach((input) => input.addEventListener('change', () => {
    const file = input.files[0];
    const preview = document.getElementById(input.dataset.avatarPreview);
    if (!file || !preview) return;
    if (file.size > 5 * 1024 * 1024) { toast('Фото має бути не більше 5 МБ'); input.value = ''; return; }
    const img = document.createElement('img');
    img.alt = 'Попередній перегляд аватара';
    const url = URL.createObjectURL(file);
    img.src = url;
    img.onload = () => URL.revokeObjectURL(url);
    preview.replaceChildren(img);
  }));
  document.querySelector('[name=skip_photo]')?.addEventListener('click', () => { const input = document.querySelector('[name=avatar]'); if (input) input.value = ''; });
  document.querySelectorAll('[data-confirm]').forEach((form) => form.addEventListener('submit', (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  document.querySelectorAll('details.dropdown').forEach((details) => {
    details.addEventListener('toggle', () => { if (details.open) document.querySelectorAll('details.dropdown').forEach((other) => { if (other !== details) other.open = false; }); });
    document.addEventListener('click', (event) => { if (!details.contains(event.target)) details.open = false; });
    details.addEventListener('keydown', (event) => { if (event.key === 'Escape') { details.open = false; details.querySelector('summary').focus(); } });
  });
})();
(() => {
  const data = document.getElementById('topic-subjects');
  const subject = document.getElementById('id_subject');
  const topic = document.getElementById('id_topic');
  if (!data || !subject || !topic) return;
  const subjects = JSON.parse(data.textContent);
  const update = () => {
    for (const option of topic.options) {
      const allowed = !option.value || String(subjects[option.value]) === subject.value;
      option.hidden = !allowed;
      option.disabled = !allowed;
    }
    if (topic.selectedOptions[0]?.disabled) topic.value = '';
  };
  subject.addEventListener('change', update);
  update();
})();
(() => {
  const trigger = document.getElementById('profile-trigger');
  const menu = document.getElementById('profile-menu');
  if (!trigger || !menu) return;
  const position = () => {
    if (!menu.matches(':popover-open')) return;
    const anchor = trigger.getBoundingClientRect();
    const collapsed = !matchMedia('(max-width: 760px)').matches && document.body.classList.contains('sidebar-collapsed');
    const left = collapsed ? anchor.right + 12 : anchor.left;
    const top = collapsed ? anchor.bottom - menu.offsetHeight : anchor.top - menu.offsetHeight - 8;
    menu.style.left = `${Math.max(8, Math.min(left, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(top, innerHeight - menu.offsetHeight - 8))}px`;
  };
  menu.addEventListener('beforetoggle', (event) => {
    trigger.setAttribute('aria-expanded', String(event.newState === 'open'));
    if (event.newState === 'open') requestAnimationFrame(position);
  });
  menu.addEventListener('toggle', position);
  window.addEventListener('resize', position);
  document.addEventListener('scroll', position, true);
})();
