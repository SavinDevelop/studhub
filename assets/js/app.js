(() => {
  'use strict';
  const stack = document.querySelector('.toast-stack');
  const setupToast = (element) => {
    let timer;
    let remaining = element.matches('.error, .warning') ? 9000 : 5500;
    let started = performance.now();
    let closing = false;
    const pause = () => { if (timer) { clearTimeout(timer); timer = null; remaining = Math.max(0, remaining - (performance.now() - started)); } };
    const dismiss = () => {
      if (closing) return;
      closing = true;
      clearTimeout(timer);
      element.classList.add('is-leaving');
      setTimeout(() => {
        if (element.contains(document.activeElement)) document.querySelector('#main')?.focus({preventScroll: true});
        element.remove();
        if (!stack.children.length && stack.matches(':popover-open')) stack.hidePopover();
      }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 250);
    };
    const resume = () => {
      clearTimeout(timer);
      timer = null;
      if (closing || document.hidden || element.matches(':hover, :focus-within')) return;
      started = performance.now();
      timer = setTimeout(dismiss, remaining);
    };
    element.querySelector('.toast-close').addEventListener('click', dismiss);
    element.addEventListener('mouseenter', pause);
    element.addEventListener('mouseleave', resume);
    element.addEventListener('focusin', pause);
    element.addEventListener('focusout', () => requestAnimationFrame(resume));
    const visibility = () => document.hidden ? pause() : resume();
    document.addEventListener('visibilitychange', visibility);
    const observer = new MutationObserver(() => {
      if (!element.isConnected) { document.removeEventListener('visibilitychange', visibility); observer.disconnect(); }
    });
    observer.observe(stack, {childList: true});
    resume();
  };
  const toast = (message, level = 'success') => {
    if (!stack) return;
    const element = document.createElement('div');
    element.className = `toast ${level}`;
    element.setAttribute('role', level === 'error' ? 'alert' : 'status');
    const text = document.createElement('span');
    text.className = 'toast-message';
    text.textContent = message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Закрити повідомлення');
    const closeIcon = document.getElementById('close-icon-template');
    if (closeIcon) close.append(closeIcon.content.cloneNode(true));
    element.append(text, close);
    stack.append(element);
    stack.showPopover?.();
    setupToast(element);
  };
  if (stack?.children.length) {
    stack.showPopover?.();
    stack.querySelectorAll('[data-toast]').forEach(setupToast);
  }
  document.querySelectorAll('[data-file-picker]').forEach((picker) => {
    const input = picker.querySelector('input[type=file]');
    const name = picker.querySelector('.file-picker-name');
    const update = () => { name.textContent = Array.from(input.files, file => file.name).join(', ') || 'Файл не вибрано'; };
    input.addEventListener('change', update);
    input.form?.addEventListener('reset', () => setTimeout(update, 0));
    update();
  });
  document.querySelectorAll('[data-url-list]').forEach((list) => {
    const rows = list.querySelector('.url-list-rows');
    let nextId = rows.children.length;
    list.querySelector('[data-url-add]').addEventListener('click', () => {
      const row = rows.firstElementChild.cloneNode(true);
      const input = row.querySelector('input');
      const base = input.id.replace(/_\d+$/, '');
      input.id = `${base}_${nextId++}`;
      input.value = '';
      input.setAttribute('aria-label', `${rows.firstElementChild.querySelector('input').getAttribute('aria-label').replace(/ \d+$/, '')} ${nextId}`);
      rows.append(row);
      input.focus();
    });
    rows.addEventListener('click', (event) => {
      const button = event.target.closest('[data-url-remove]');
      if (!button) return;
      const row = button.closest('.url-list-row');
      if (rows.children.length === 1) { row.querySelector('input').value = ''; row.querySelector('input').focus(); }
      else {
        const focus = row.nextElementSibling || row.previousElementSibling;
        const firstId = rows.firstElementChild.querySelector('input').id;
        const isFirst = row === rows.firstElementChild;
        row.remove();
        if (isFirst) rows.firstElementChild.querySelector('input').id = firstId;
        focus.querySelector('input').focus();
      }
    });
  });
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
  document.querySelectorAll('dialog[data-auto-open]').forEach((dialog) => dialog.showModal());
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
    if (file.size > 5 * 1024 * 1024) { toast('Фото має бути не більше 5 МБ', 'error'); input.value = ''; input.dispatchEvent(new Event('change', {bubbles: true})); return; }
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
