(function () {
  'use strict';

  var PE = window.ProjectEditor;
  if (!PE) return;

  var pData = document.getElementById('projectData');
  var isAdmin = pData ? pData.getAttribute('data-admin') === 'true' : false;

  function initCollaboratorsModal(modal) {
    var inviteBtn = modal.querySelector('#inviteBtn');
    var emailInput = modal.querySelector('#inviteEmail');
    var roleSelect = modal.querySelector('#inviteRole');
    if (!inviteBtn || !emailInput || !roleSelect) return;
    inviteBtn.addEventListener('click', function () {
      var email = emailInput.value.trim();
      var role = roleSelect.value;
      if (!email) return;
      inviteBtn.disabled = true;

      PE.fetchApi(PE.apiUrl('collaborators/invite/'), {
        method: 'POST',
        body: JSON.stringify({ email: email, role: role }),
      }).then(function (r) {
        if (r.ok) {
          window.showToast(gettext('Collaborator invited'), 'success');
          return window.Modal.refresh();
        }
        inviteBtn.disabled = false;
        return r.json().then(function (d) {
          window.showToast(d.error || gettext('Failed to invite'), 'danger');
        });
      });
    });
  }

  document.addEventListener('modal:shown', function (e) {
    if (e.detail && e.detail.name === 'collaborators') initCollaboratorsModal(e.target);
  });

  document.addEventListener('change', function (e) {
    if (e.target.classList.contains('collab-role-select')) {
      var select = e.target;
      var membershipId = select.getAttribute('data-id');
      var role = select.value;
      var previousRole = select.getAttribute('data-current-role') || '';
      var roleLabel = select.options[select.selectedIndex].text;
      var nameEl = select.parentNode.querySelector('.fw-semibold');
      var collaboratorName = nameEl ? nameEl.textContent : gettext('this collaborator');
      window.showConfirmModal({
        title: gettext('Change Role'),
        bodyText: interpolate(gettext('Change the role of %(name)s to %(role)s?'), { name: collaboratorName, role: roleLabel }, true),
        confirmText: gettext('Change'),
        confirmClass: 'btn-primary',
        onConfirm: function () {
          PE.fetchApi(PE.apiUrl('collaborators/' + membershipId + '/'), {
            method: 'PATCH',
            body: JSON.stringify({ role: role }),
          }).then(function (r) {
            if (r.ok) {
              select.setAttribute('data-current-role', role);
              window.showToast(gettext('Role updated'), 'success');
              return;
            }
            select.value = previousRole;
            return r.json().catch(function () { return {}; }).then(function (d) {
              window.showToast(d.error || d.detail || gettext('Failed to update role'), 'danger');
            });
          });
        },
        onCancel: function () { select.value = previousRole; }
      });
    }
  });

  document.addEventListener('click', function (e) {
    var removeBtn = e.target.closest('.collab-remove-btn');
    if (removeBtn) {
      var membershipId = removeBtn.getAttribute('data-id');
      window.showConfirmModal({
        title: gettext('Remove Collaborator'),
        body: gettext('Are you sure you want to remove this collaborator?'),
        confirmText: gettext('Remove'),
        onConfirm: function () {
          PE.fetchApi(PE.apiUrl('collaborators/' + membershipId + '/'), {
            method: 'DELETE',
          }).then(function (r) {
            if (r.ok) {
              window.showToast(gettext('Collaborator removed'), 'success');
              window.Modal.refresh();
              return;
            }
            return r.json().catch(function () { return {}; }).then(function (d) {
              window.showToast(d.error || d.detail || gettext('Failed to remove collaborator'), 'danger');
            });
          });
        }
      });
    }
  });

  var openAuditBtn = document.getElementById('openAuditBtn');
  var auditPanel = document.getElementById('auditPanel');
  var auditBackdrop = document.getElementById('auditBackdrop');
  var closeAuditBtn = document.getElementById('closeAuditBtn');

  function openAudit() {
    if (auditPanel) auditPanel.classList.add('show');
    if (auditBackdrop) auditBackdrop.classList.add('show');
    loadAuditLog();
  }

  function closeAudit() {
    if (auditPanel) auditPanel.classList.remove('show');
    if (auditBackdrop) auditBackdrop.classList.remove('show');
  }

  if (openAuditBtn) openAuditBtn.addEventListener('click', function (e) { e.preventDefault(); openAudit(); });
  if (closeAuditBtn) closeAuditBtn.addEventListener('click', closeAudit);
  if (auditBackdrop) auditBackdrop.addEventListener('click', closeAudit);

  var auditFilterType = document.getElementById('auditFilterType');
  var auditFilterUser = document.getElementById('auditFilterUser');

  if (auditFilterType) auditFilterType.addEventListener('change', loadAuditLog);
  if (auditFilterUser) auditFilterUser.addEventListener('change', loadAuditLog);

  function loadAuditLog() {
    var body = document.getElementById('auditBody');
    var countEl = document.getElementById('auditCount');
    if (!body) return;
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border spinner-border-sm"></div></div>';

    var params = [];
    if (auditFilterType && auditFilterType.value !== 'all') params.push('action=' + auditFilterType.value);
    if (auditFilterUser && auditFilterUser.value) params.push('user=' + auditFilterUser.value);
    var qs = params.length > 0 ? '?' + params.join('&') : '';

    PE.fetchApi(PE.apiUrl('audit-log/' + qs)).then(function (r) {
      return r.json();
    }).then(function (data) {
      var entries = data.results || [];
      if (countEl) countEl.textContent = entries.length;
      if (entries.length === 0) {
        body.innerHTML = '<div class="text-muted small text-center py-4">' + gettext('No audit entries') + '</div>';
        return;
      }
      body.innerHTML = entries.map(function (entry) {
        return '<div class="audit-entry">' +
          '<div class="audit-entry-icon bg-opacity-10 ' + PE.escapeHtml(entry.icon_color) + '" style="background:var(--bs-' + iconBg(entry.icon_color) + '-rgb)">' +
            '<i class="bi ' + PE.escapeHtml(entry.icon) + '"></i>' +
          '</div>' +
          '<div class="audit-entry-content">' +
            '<div class="audit-entry-text"><strong>' + PE.escapeHtml(entry.user_name) + '</strong> ' + PE.escapeHtml(entry.action_display.toLowerCase()) + ' ' + PE.escapeHtml(entry.target_type.toLowerCase()) + ' <strong' + (entry.target_type === 'Item' ? ' class="text-nowrap"' : '') + '>' + PE.escapeHtml(entry.target_id) + '</strong></div>' +
            '<div class="audit-entry-time">' + PE.formatDate(entry.created_at) + '</div>' +
          '</div>' +
        '</div>';
      }).join('');
    });
  }

  function iconBg(textClass) {
    var map = {
      'text-primary': 'primary',
      'text-success': 'success',
      'text-danger': 'danger',
      'text-warning': 'warning',
      'text-info': 'info',
      'text-secondary': 'secondary',
      'text-muted': 'secondary',
    };
    return map[textClass] || 'secondary';
  }

  var openVersionBtn = document.getElementById('openVersionBtn');
  var versionPanel = document.getElementById('versionPanel');
  var versionBackdrop = document.getElementById('versionBackdrop');
  var closeVersionBtn = document.getElementById('closeVersionBtn');

  function openVersions() {
    if (versionPanel) versionPanel.classList.add('show');
    if (versionBackdrop) versionBackdrop.classList.add('show');
    loadVersionHistory();
  }

  function closeVersions() {
    if (versionPanel) versionPanel.classList.remove('show');
    if (versionBackdrop) versionBackdrop.classList.remove('show');
  }

  if (openVersionBtn) openVersionBtn.addEventListener('click', function (e) { e.preventDefault(); openVersions(); });
  if (closeVersionBtn) closeVersionBtn.addEventListener('click', closeVersions);
  if (versionBackdrop) versionBackdrop.addEventListener('click', closeVersions);

  function loadVersionHistory(page) {
    var container = document.getElementById('versionHistoryList');
    if (!container) return;
    page = page || 1;
    var loadMore = container.querySelector('.version-load-more');
    if (page === 1) {
      container.innerHTML = '<div class="text-center py-4"><div class="spinner-border spinner-border-sm"></div></div>';
    } else if (loadMore) {
      loadMore.disabled = true;
    }

    PE.fetchApi(PE.apiUrl('versions/?page=' + page)).then(function (r) {
      return r.json();
    }).then(function (data) {
      var versions = data.results || data;
      if (page === 1 && versions.length === 0) {
        container.innerHTML = '<div class="text-muted small text-center py-4">' + gettext('No version history') + '</div>';
        return;
      }
      var html = versions.map(function (v) {
        return '<div class="version-entry border-bottom py-2">' +
          '<div class="d-flex align-items-center justify-content-between">' +
            '<div>' +
              '<span class="fw-semibold small">' + interpolate(gettext('v%(number)s'), { number: PE.escapeHtml(v.version_number) }, true) + '</span>' +
              '<span class="small text-muted ms-2">' + interpolate(gettext('by %(name)s'), { name: PE.escapeHtml(v.changed_by_name) }, true) + '</span>' +
            '</div>' +
            '<span class="small text-muted">' + PE.formatDate(v.changed_at) + '</span>' +
          '</div>' +
          '<div class="small text-muted mt-1">' + PE.escapeHtml(v.change_summary) + ' ' + interpolate(ngettext('(%(count)s items)', '(%(count)s items)', v.item_count), { count: v.item_count }, true) + '</div>' +
          (isAdmin ? '<button class="btn btn-sm btn-link p-0 mt-1 version-restore-btn" data-id="' + v.public_key + '">' + gettext('Restore this version') + '</button>' : '') +
        '</div>';
      }).join('');
      if (data.next) {
        html += '<button type="button" class="btn btn-sm btn-outline-secondary w-100 mt-2 version-load-more" data-page="' + (page + 1) + '">' + gettext('Load more') + '</button>';
      }
      if (page === 1) {
        container.innerHTML = html;
      } else {
        if (loadMore) loadMore.remove();
        container.insertAdjacentHTML('beforeend', html);
      }
    });
  }

  document.addEventListener('click', function (e) {
    var loadMore = e.target.closest('.version-load-more');
    if (loadMore) loadVersionHistory(parseInt(loadMore.getAttribute('data-page')));
  });

  document.addEventListener('click', function (e) {
    var restoreBtn = e.target.closest('.version-restore-btn');
    if (restoreBtn) {
      var versionId = restoreBtn.getAttribute('data-id');
      window.showConfirmModal({
        title: gettext('Restore Version'),
        body: gettext('Restore this version? Current items will be replaced. This cannot be undone.'),
        confirmText: gettext('Restore'),
        confirmClass: 'btn-warning',
        onConfirm: function () {
          PE.fetchApi(PE.apiUrl('versions/' + versionId + '/restore/'), {
            method: 'POST',
          }).then(function (r) {
            if (r.ok) {
              window.showToast(gettext('Version restored successfully'), 'success');
              window.location.reload();
            } else {
              r.json().then(function (data) {
                window.showToast(data.error || gettext('Failed to restore version'), 'danger');
              });
            }
          });
        }
      });
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeAudit();
      closeVersions();
    }
  });

})();
