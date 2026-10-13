(function () {
    'use strict';

    var authenticationForm = document.getElementById('authenticationForm');
    if (authenticationForm) {
        var switches = authenticationForm.querySelectorAll('input[type="checkbox"]');
        authenticationForm.addEventListener('change', function (event) {
            var target = event.target;
            if (target.type !== 'checkbox' || target.checked) return;
            var anyOn = Array.prototype.some.call(switches, function (input) { return input.checked; });
            if (anyOn) return;
            target.checked = true;
            if (window.showToast) window.showToast(authenticationForm.getAttribute('data-both-off'), 'danger');
        });
    }

    function serialize(form) {
        return new URLSearchParams(new FormData(form)).toString();
    }

    document.querySelectorAll('form[data-dirty-form]').forEach(function (form) {
        var button = form.querySelector('button[type="submit"]');
        if (!button) return;
        var saved = serialize(form);
        var update = function () { button.disabled = serialize(form) === saved; };
        form.addEventListener('input', update);
        form.addEventListener('change', update);
        update();
    });

    document.querySelectorAll('[data-depends-on]').forEach(function (input) {
        var toggle = document.getElementById(input.getAttribute('data-depends-on'));
        if (!toggle) return;
        var field = input.closest('.settings-field') || input;
        var apply = function () {
            input.readOnly = !toggle.checked;
            field.classList.toggle('is-locked', !toggle.checked);
        };
        toggle.addEventListener('change', apply);
        apply();
    });

    var search = document.getElementById('adminUserSearch');
    if (search) {
        search.addEventListener('search', function () {
            if (search.value === '' && search.defaultValue !== '') search.form.requestSubmit();
        });
        search.form.addEventListener('submit', function () {
            if (search.value.trim() === '') search.disabled = true;
        });
    }
})();
