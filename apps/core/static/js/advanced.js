(function () {
  'use strict';

  var PE = window.ProjectEditor;
  if (!PE) return;

  var pData = document.getElementById('projectData');
  var isEditor = pData ? pData.getAttribute('data-editor') === 'true' : false;

  var filterStatus = document.getElementById('filterStatus');
  var filterPriority = document.getElementById('filterPriority');
  var filterTag = document.getElementById('advFilterTag');
  var filterApplyBtn = document.getElementById('advFilterApplyBtn');
  var filterClearBtn = document.getElementById('advFilterClearBtn');
  var filterBadge = document.getElementById('filterBadge');

  var itemSearch = document.getElementById('itemSearch');
  var itemsEmpty = document.getElementById('itemsEmpty');
  var itemCount = document.getElementById('itemCount');

  function rowMatches(row, q, status, priority, tag) {
    if (status && row.getAttribute('data-status') !== status) return false;
    if (priority && row.getAttribute('data-priority') !== priority) return false;
    if (tag) {
      var hasTag = Array.prototype.some.call(row.querySelectorAll('.col-tags .badge'), function (t) {
        return t.textContent.trim() === tag;
      });
      if (!hasTag) return false;
    }
    if (q) {
      var itemId = (row.getAttribute('data-item-id') || '').toLowerCase();
      var text = ((row.querySelector('.col-text') || {}).textContent || '').toLowerCase();
      if (itemId.indexOf(q) === -1 && text.indexOf(q) === -1) return false;
    }
    return true;
  }

  function applyView() {
    var status = filterStatus ? filterStatus.value : '';
    var priority = filterPriority ? filterPriority.value : '';
    var tag = filterTag ? filterTag.value : '';
    var q = itemSearch ? itemSearch.value.trim().toLowerCase() : '';
    var narrowing = !!(status || priority || tag || q);

    var headers = document.querySelectorAll('#itemsTable tbody tr.section-header-row, #itemsTable tbody tr.subsection-header-row');
    var numberBySection = {};
    Array.prototype.forEach.call(headers, function (hdr) {
      numberBySection[hdr.getAttribute('data-section')] = hdr.getAttribute('data-number') || '';
    });

    var rows = document.querySelectorAll('#itemsTable tbody tr.item-row[data-key]');
    var shownNumbers = [];
    var shown = 0;
    Array.prototype.forEach.call(rows, function (row) {
      var show = rowMatches(row, q, status, priority, tag);
      row.style.display = show ? '' : 'none';
      if (show) {
        shown++;
        shownNumbers.push(numberBySection[row.getAttribute('data-section')] || '');
      } else {
        var cb = row.querySelector('.bulk-checkbox');
        if (cb && cb.checked) {
          cb.checked = false;
          cb.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    });

    Array.prototype.forEach.call(headers, function (hdr) {
      var number = hdr.getAttribute('data-number') || '';
      var keep = !narrowing || shownNumbers.some(function (n) {
        return n === number || n.indexOf(number + '.') === 0;
      });
      hdr.style.display = keep ? '' : 'none';
    });

    if (itemsEmpty) itemsEmpty.hidden = !(narrowing && shown === 0 && rows.length > 0);
    if (itemCount) {
      var total = rows.length;
      itemCount.textContent = narrowing
        ? interpolate(ngettext('%(shown)s of %(total)s item', '%(shown)s of %(total)s items', total), { shown: shown, total: total }, true)
        : interpolate(ngettext('%(count)s item', '%(count)s items', total), { count: total }, true);
    }

    var activeCount = (status ? 1 : 0) + (priority ? 1 : 0) + (tag ? 1 : 0);
    if (filterBadge) {
      filterBadge.textContent = activeCount;
      filterBadge.classList.toggle('d-none', activeCount === 0);
    }
  }

  function applyFilters() {
    applyView();
  }

  function clearFilters() {
    if (filterStatus) filterStatus.value = '';
    if (filterPriority) filterPriority.value = '';
    if (filterTag) filterTag.value = '';
    applyView();
  }

  if (filterApplyBtn) filterApplyBtn.addEventListener('click', applyFilters);
  if (filterClearBtn) filterClearBtn.addEventListener('click', clearFilters);

  var clearAllFiltersBtn = document.getElementById('clearAllFiltersBtn');
  if (clearAllFiltersBtn) {
    clearAllFiltersBtn.addEventListener('click', function () {
      if (itemSearch) itemSearch.value = '';
      clearFilters();
    });
  }

  if ((filterStatus && filterStatus.value) || (filterPriority && filterPriority.value) || (filterTag && filterTag.value)) {
    applyFilters();
  }

  if (itemSearch) {
    var searchTimeout;
    itemSearch.addEventListener('input', function () {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(applyView, 200);
    });
    itemSearch.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && itemSearch.value) {
        e.preventDefault();
        itemSearch.value = '';
        clearTimeout(searchTimeout);
        applyView();
      }
    });
  }

  var bulkToggleBtn = document.getElementById('bulkToggleBtn');
  var bulkToolbar = document.getElementById('bulkToolbar');
  var bulkMode = false;
  var bulkSelected = [];

  if (bulkToggleBtn && isEditor) {
    bulkToggleBtn.addEventListener('click', function () {
      bulkMode = !bulkMode;
      if (bulkToolbar) bulkToolbar.classList.toggle('d-none', !bulkMode);
      bulkToggleBtn.setAttribute('aria-pressed', bulkMode ? 'true' : 'false');
      if (bulkSelectAll) bulkSelectAll.checked = false;
      toggleBulkCheckboxes(bulkMode);
      bulkSelected = [];
      updateBulkCount();
    });
  }

  function toggleBulkCheckboxes(show) {
    var rows = document.querySelectorAll('#itemsTable tbody tr.item-row:not(.section-header-row):not(.subsection-header-row)');
    rows.forEach(function (row) {
      var dragHandle = row.querySelector('.drag-handle');
      if (!dragHandle) return;
      if (show) {
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'form-check-input bulk-checkbox';
        cb.setAttribute('data-id', row.getAttribute('data-id'));
        dragHandle.innerHTML = '';
        dragHandle.appendChild(cb);
      } else {
        dragHandle.innerHTML = '<i class="bi bi-grip-vertical"></i>';
      }
    });
  }

  document.addEventListener('change', function (e) {
    if (e.target.classList.contains('bulk-checkbox')) {
      var pk = parseInt(e.target.getAttribute('data-id'));
      if (e.target.checked) {
        if (bulkSelected.indexOf(pk) === -1) bulkSelected.push(pk);
      } else {
        bulkSelected = bulkSelected.filter(function (id) { return id !== pk; });
      }
      updateBulkCount();
    }
  });

  var bulkSelectAll = document.getElementById('bulkSelectAll');
  if (bulkSelectAll) {
    bulkSelectAll.addEventListener('change', function () {
      var cbs = document.querySelectorAll('.bulk-checkbox');
      bulkSelected = [];
      cbs.forEach(function (cb) {
        var row = cb.closest('tr');
        var visible = !row || row.style.display !== 'none';
        cb.checked = bulkSelectAll.checked && visible;
        if (cb.checked) {
          bulkSelected.push(parseInt(cb.getAttribute('data-id')));
        }
      });
      updateBulkCount();
    });
  }

  function updateBulkCount() {
    var el = document.getElementById('bulkCount');
    if (el) el.textContent = interpolate(ngettext('%(count)s selected', '%(count)s selected', bulkSelected.length), { count: bulkSelected.length }, true);
  }

  function bulkAction(action, value) {
    if (bulkSelected.length === 0) return;
    PE.fetchApi(PE.apiUrl('items/bulk/'), {
      method: 'POST',
      body: JSON.stringify({ item_ids: bulkSelected, action: action, value: value }),
    }).then(function (r) {
      if (r.ok) {
        window.showToast(gettext('Bulk operation completed'), 'success');
        window.location.reload();
      } else {
        window.showToast(gettext('Bulk operation failed'), 'danger');
      }
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-bulk-status]');
    if (btn) { bulkAction('set_status', btn.getAttribute('data-bulk-status')); return; }

    btn = e.target.closest('[data-bulk-priority]');
    if (btn) { bulkAction('set_priority', btn.getAttribute('data-bulk-priority')); return; }

    btn = e.target.closest('[data-bulk-tag]');
    if (btn) { bulkAction('add_tag', btn.getAttribute('data-bulk-tag')); return; }
  });

  var bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener('click', function () {
      if (bulkSelected.length === 0) return;
      window.showConfirmModal({
        title: gettext('Delete Items'),
        body: interpolate(ngettext('Delete %(count)s item? This cannot be undone.', 'Delete %(count)s items? This cannot be undone.', bulkSelected.length), { count: '<strong>' + bulkSelected.length + '</strong>' }, true),
        confirmText: gettext('Delete'),
        onConfirm: function () {
          bulkAction('delete', '');
        }
      });
    });
  }

  document.addEventListener('click', function (e) {
    var viewItem = e.target.closest('.saved-view-item');
    if (viewItem) {
      var filtersStr = viewItem.getAttribute('data-filters');
      try {
        var filters = JSON.parse(filtersStr);
        if (filterStatus) filterStatus.value = filters.status || '';
        if (filterPriority) filterPriority.value = filters.priority || '';
        if (filterTag) filterTag.value = filters.tag || '';
        applyFilters();
      } catch (err) {}
    }
  });

  var savedViewsMenu = document.getElementById('savedViewsMenu');
  if (savedViewsMenu) {
    savedViewsMenu.addEventListener('menu:select', function (e) {
      if (e.detail.action !== 'delete-view') return;
      var key = e.detail.value;
      var name = e.detail.item.textContent.trim();
      window.showConfirmModal({
        title: gettext('Delete View'),
        bodyText: interpolate(gettext('Delete the saved view "%(name)s"?'), { name: name }, true),
        confirmText: gettext('Delete'),
        onConfirm: function () {
          PE.fetchApi(PE.apiUrl('saved-views/' + key + '/'), { method: 'DELETE' }).then(function (r) {
            if (r.ok) window.location.reload();
            else window.showToast(gettext('Failed to delete view'), 'danger');
          });
        }
      });
    });
  }

  function initSaveViewModal(modal) {
    var submit = modal.querySelector('#saveViewSubmit');
    var nameInput = modal.querySelector('#saveViewName');
    if (!submit || !nameInput) return;
    submit.addEventListener('click', function () {
      var name = nameInput.value.trim();
      if (!name) return;
      var filters = {};
      if (filterStatus && filterStatus.value) filters.status = filterStatus.value;
      if (filterPriority && filterPriority.value) filters.priority = filterPriority.value;
      if (filterTag && filterTag.value) filters.tag = filterTag.value;
      submit.disabled = true;

      PE.fetchApi(PE.apiUrl('saved-views/'), {
        method: 'POST',
        body: JSON.stringify({ name: name, filters: filters }),
      }).then(function (r) {
        if (r.ok) {
          window.Modal.close('confirmed');
          window.showToast(gettext('View saved'), 'success');
          window.location.reload();
        } else {
          submit.disabled = false;
          window.showToast(gettext('Failed to save view'), 'danger');
        }
      });
    });
  }

  function initAddLinkModal(modal) {
    var linkTargetSearch = modal.querySelector('#linkTargetSearch');
    var linkTargetResults = modal.querySelector('#linkTargetResults');
    var linkTargetId = modal.querySelector('#linkTargetId');
    var linkTypeSelect = modal.querySelector('#linkType');
    var submit = modal.querySelector('#addLinkSubmit');
    if (!linkTargetSearch || !linkTargetResults || !linkTargetId || !submit) return;

    var linkSearchTimeout;
    linkTargetSearch.addEventListener('input', function () {
      clearTimeout(linkSearchTimeout);
      linkSearchTimeout = setTimeout(function () {
        var q = linkTargetSearch.value.trim();
        if (q.length < 2) {
          linkTargetResults.innerHTML = '';
          return;
        }
        PE.fetchApi(PE.apiUrl('items/search/?q=' + encodeURIComponent(q))).then(function (r) {
          return r.json();
        }).then(function (items) {
          linkTargetResults.innerHTML = items.map(function (item) {
            return '<button type="button" class="btn btn-sm btn-light w-100 text-start mb-1 link-target-option" data-pk="' + item.id + '">' +
              '<span class="fw-semibold">' + PE.escapeHtml(item.item_id) + '</span> ' +
              '<span class="small text-muted">' + PE.escapeHtml(PE.stripHtml(item.text).substring(0, 60)) + '</span>' +
              '</button>';
          }).join('');
        });
      }, 300);
    });

    linkTargetResults.addEventListener('click', function (e) {
      var opt = e.target.closest('.link-target-option');
      if (!opt) return;
      linkTargetId.value = opt.getAttribute('data-pk');
      linkTargetSearch.value = opt.querySelector('.fw-semibold').textContent;
      linkTargetResults.innerHTML = '';
    });

    submit.addEventListener('click', function () {
      var sourceItemPk = PE.selectedItemPk();
      var sourceItemKey = PE.selectedItemKey();
      var targetPk = linkTargetId.value;
      var linkType = linkTypeSelect ? linkTypeSelect.value : 'traces-to';
      if (!sourceItemPk || !targetPk) {
        window.showToast(gettext('Please select a target item'), 'warning');
        return;
      }
      submit.disabled = true;
      PE.fetchApi(PE.apiUrl('items/' + sourceItemKey + '/links/'), {
        method: 'POST',
        body: JSON.stringify({
          source_item: sourceItemPk,
          target_item: parseInt(targetPk),
          link_type: linkType,
        }),
      }).then(function (r) {
        if (r.ok) {
          window.Modal.close('confirmed');
          PE.loadItemDetail(sourceItemKey);
          window.showToast(gettext('Link added'), 'success');
        } else {
          submit.disabled = false;
          window.showToast(gettext('Failed to add link'), 'danger');
        }
      });
    });
  }

  document.addEventListener('modal:shown', function (e) {
    if (!e.detail) return;
    if (e.detail.name === 'save_view') initSaveViewModal(e.target);
    if (e.detail.name === 'add_link') initAddLinkModal(e.target);
  });

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'A') {
      e.preventDefault();
      if (bulkToggleBtn && isEditor) bulkToggleBtn.click();
    }
  });

})();
