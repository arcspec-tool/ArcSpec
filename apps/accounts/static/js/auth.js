(function () {
  'use strict';

  function passwordInput(button) {
    return document.getElementById(button.getAttribute('aria-controls'));
  }

  function setVisible(button, show) {
    var input = passwordInput(button);
    if (!input) return;
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', show ? 'true' : 'false');
    button.title = show ? gettext('Hide password') : gettext('Show password');
    button.querySelector('.bi').className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
  }

  function setBusy(control) {
    if (!control || !control.dataset.busyLabel || control.dataset.busy === 'true') return;
    control.dataset.busy = 'true';
    control.idleChildren = Array.prototype.map.call(control.childNodes, function (node) { return node.cloneNode(true); });
    var spinner = document.createElement('span');
    spinner.className = 'spinner-border spinner-border-sm';
    spinner.setAttribute('aria-hidden', 'true');
    control.replaceChildren(spinner, document.createTextNode(control.dataset.busyLabel));
    control.setAttribute('aria-disabled', 'true');
    control.classList.add('is-busy');
  }

  function clearBusy(control) {
    control.replaceChildren.apply(control, control.idleChildren || []);
    delete control.dataset.busy;
    control.removeAttribute('aria-disabled');
    control.classList.remove('is-busy');
  }

  document.querySelectorAll('[data-password-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      setVisible(button, button.getAttribute('aria-pressed') !== 'true');
      var input = passwordInput(button);
      if (input) input.focus();
    });
  });

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form.hasAttribute('data-busy-form')) return;
    if (form.dataset.submitting === 'true') {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = 'true';
    form.querySelectorAll('[data-password-toggle]').forEach(function (button) { setVisible(button, false); });
    setBusy(event.submitter || form.querySelector('[type="submit"]'));
  });

  document.addEventListener('click', function (event) {
    var link = event.target.closest('a[data-busy-label]');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (link.dataset.busy === 'true') {
      event.preventDefault();
      return;
    }
    setBusy(link);
  });

  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) return;
    document.querySelectorAll('[data-busy="true"]').forEach(clearBusy);
    document.querySelectorAll('form[data-submitting]').forEach(function (form) { delete form.dataset.submitting; });
  });
})();
