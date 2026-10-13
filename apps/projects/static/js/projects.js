(function () {
    'use strict';

    function init() {
        initSortDropdown();
        initSearchClear();
        initTableRowClick();
    }

    function initSortDropdown() {
        var sortSelect = document.getElementById('projectSort');
        if (!sortSelect) return;
        sortSelect.addEventListener('change', function () {
            var url = new URL(window.location.href);
            url.searchParams.set('sort', this.value);
            url.searchParams.delete('page');
            window.location.href = url.toString();
        });
    }

    function initSearchClear() {
        var input = document.getElementById('localProjectSearch');
        if (!input) return;
        input.addEventListener('search', function () {
            if (input.value === '' && input.defaultValue !== '') input.form.requestSubmit();
        });
        input.form.addEventListener('submit', function () {
            if (input.value.trim() === '') input.disabled = true;
        });
    }

    function initTableRowClick() {
        var rows = document.querySelectorAll('tr[data-href]');
        for (var i = 0; i < rows.length; i++) {
            rows[i].addEventListener('click', function (e) {
                if (e.target.closest('.project-actions') || e.target.closest('.menu') || e.target.closest('form') || e.target.closest('a')) return;
                window.location.href = this.getAttribute('data-href');
            });
        }
    }

    function updateSwatchSelection(picker) {
        var labels = picker.querySelectorAll('.color-swatch-label');
        for (var i = 0; i < labels.length; i++) {
            var radio = labels[i].querySelector('input[type="radio"]');
            var swatch = labels[i].querySelector('.color-swatch');
            if (radio && swatch) swatch.classList.toggle('color-swatch-selected', radio.checked);
        }
    }

    document.addEventListener('modal:shown', function (e) {
        if (!e.detail || (e.detail.name !== 'project_create' && e.detail.name !== 'project_edit')) return;
        var pickers = e.target.querySelectorAll('.color-picker');
        for (var p = 0; p < pickers.length; p++) {
            updateSwatchSelection(pickers[p]);
            pickers[p].addEventListener('change', function (ev) {
                updateSwatchSelection(ev.currentTarget);
            });
        }
    });

    init();
})();
