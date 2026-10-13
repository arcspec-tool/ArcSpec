(function () {
  'use strict';

  var projectDataEl = document.getElementById('projectData');
  var projectSlug = projectDataEl ? projectDataEl.getAttribute('data-slug') : '';
  var projectId = projectDataEl ? parseInt(projectDataEl.getAttribute('data-id')) : 0;
  var userRole = projectDataEl ? projectDataEl.getAttribute('data-role') : '';
  var isEditor = projectDataEl ? projectDataEl.getAttribute('data-editor') === 'true' : false;
  var isAdmin = projectDataEl ? projectDataEl.getAttribute('data-admin') === 'true' : false;
  var isArchived = projectDataEl ? projectDataEl.getAttribute('data-archived') === 'true' : false;
  var currentUserId = projectDataEl ? parseInt(projectDataEl.getAttribute('data-user-id')) : 0;

  var collapseBtn = document.getElementById('sidebarCollapseBtn');
  if (collapseBtn) {
    var collapseIcon = collapseBtn.querySelector('i');
    var sidebarState = localStorage.getItem('sidebarCollapsed');
    var shouldCollapse = sidebarState === null || sidebarState === '1';
    if (shouldCollapse) {
      document.body.classList.add('sidebar-collapsed');
      if (collapseIcon) { collapseIcon.className = 'bi bi-chevron-bar-right'; }
      collapseBtn.title = gettext('Expand sidebar');
    }
    var sidebarTooltips = [];
    function updateSidebarTooltips() {
      sidebarTooltips.forEach(function (t) { t.dispose(); });
      sidebarTooltips = [];
      if (document.body.classList.contains('sidebar-collapsed')) {
        var links = document.querySelectorAll('#sidebar .sidebar-link, #sidebar .sidebar-signout');
        for (var i = 0; i < links.length; i++) {
          var tt = new bootstrap.Tooltip(links[i], {
            placement: 'right',
            trigger: 'hover',
            container: 'body'
          });
          sidebarTooltips.push(tt);
        }
      }
    }
    if (shouldCollapse) updateSidebarTooltips();

    collapseBtn.addEventListener('click', function () {
      document.body.classList.toggle('sidebar-collapsed');
      var collapsed = document.body.classList.contains('sidebar-collapsed');
      localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0');
      if (collapseIcon) {
        collapseIcon.className = collapsed ? 'bi bi-chevron-bar-right' : 'bi bi-chevron-bar-left';
      }
      collapseBtn.title = collapsed ? gettext('Expand sidebar') : gettext('Collapse sidebar');
      updateSidebarTooltips();
    });
  }

  function getCsrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function apiUrl(path) {
    return '/api/projects/' + projectSlug + '/' + path;
  }

  function fetchApi(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    options.headers['X-CSRFToken'] = getCsrf();
    if (!options.headers['Content-Type'] && !(options.body instanceof FormData)) {
      options.headers['Content-Type'] = 'application/json';
    }
    options.credentials = 'same-origin';
    return fetch(url, options);
  }

  function fetchAllPages(path) {
    var rows = [];
    function load(page) {
      return fetchApi(apiUrl(path + (path.indexOf('?') === -1 ? '?' : '&') + 'page=' + page)).then(function (r) {
        if (!r.ok) throw new Error(gettext('The server refused the request.'));
        return r.json();
      }).then(function (data) {
        if (!data.results) return data;
        rows = rows.concat(data.results);
        return data.next ? load(page + 1) : rows;
      });
    }
    return load(1);
  }

  document.addEventListener('focusin', function (e) {
    if (e.target.closest('.tox-tinymce-aux, .tox-tinymce, .tox-dialog')) {
      e.stopImmediatePropagation();
    }
  });

  var TINYMCE_CONFIG = {
    menubar: false,
    statusbar: false,
    plugins: 'table lists',
    toolbar: 'bold italic underline strikethrough | bullist numlist | table | removeformat',
    height: 250,
    promotion: false,
    branding: false,
    license_key: 'gpl',
    content_css: ['default', 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'],
    content_style: 'body { font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; font-size: 1rem; }',
    formats: {
      underline: { inline: 'u' },
      strikethrough: { inline: 's' },
    },
  };

  function initTinyMCE(targetId, callback) {
    if (typeof tinymce === 'undefined') {
      if (callback) callback();
      return;
    }
    var target = document.getElementById(targetId);
    if (!target) return;
    var existing = tinymce.get(targetId);
    if (existing) existing.destroy();
    var h = (TINYMCE_CONFIG.height || 250) + 'px';
    target.style.height = h;
    target.style.opacity = '0';
    var wrapper = target.parentNode;
    wrapper.style.position = 'relative';
    var loader = wrapper.querySelector('.tinymce-loader');
    if (!loader) {
      loader = document.createElement('div');
      loader.className = 'tinymce-loader';
      loader.style.height = h;
      loader.innerHTML = '<div class="spinner-border spinner-border-sm text-secondary" role="status"><span class="visually-hidden">' + gettext('Loading editor') + '</span></div>';
      wrapper.appendChild(loader);
    }
    var config = Object.assign({}, TINYMCE_CONFIG, {
      target: target,
      init_instance_callback: function (editor) {
        if (loader) loader.remove();
        if (callback) callback(editor);
      },
    });
    tinymce.init(config);
  }

  function destroyTinyMCE(targetId) {
    if (typeof tinymce === 'undefined') return;
    var editor = tinymce.get(targetId);
    if (editor) editor.destroy();
    var target = document.getElementById(targetId);
    if (target) {
      var loader = target.parentNode.querySelector('.tinymce-loader');
      if (loader) loader.remove();
    }
  }

  function getTinyMCEContent(targetId) {
    if (typeof tinymce === 'undefined') {
      var el = document.getElementById(targetId);
      return el ? el.value : '';
    }
    var editor = tinymce.get(targetId);
    return editor ? editor.getContent() : '';
  }

  function setTinyMCEContent(targetId, content) {
    if (typeof tinymce === 'undefined') {
      var el = document.getElementById(targetId);
      if (el) el.value = content;
      return;
    }
    var editor = tinymce.get(targetId);
    if (editor) editor.setContent(content || '');
  }

  function stripHtml(html) {
    if (!html) return '';
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    return tmp.textContent || '';
  }

  function hasComplexHtml(html) {
    if (!html) return false;
    var complexTags = /<(table|thead|tbody|tr|td|th|ul|ol|li|h[1-6]|img|blockquote|pre|code|iframe|hr|br)\b/i;
    if (complexTags.test(html)) return true;
    var inlineTags = /<(strong|b|em|i|u|a|span|sub|sup|mark|s|del)\b/i;
    if (inlineTags.test(html)) return true;
    var pCount = (html.match(/<p[\s>]/gi) || []).length;
    if (pCount > 1) return true;
    return false;
  }

  var replyToCommentId = null;
  var selectedItemPk = null;
  var selectedItemKey = null;
  var selectedItemRow = null;

  var treeNav = document.getElementById('treeNav');
  if (treeNav) {
    treeNav.addEventListener('click', function (e) {
      var toggle = e.target.closest('.tree-toggle');
      if (toggle) {
        var expanded = toggle.getAttribute('data-expanded') === 'true';
        var node = toggle.closest('.tree-node');
        var children = node.nextElementSibling;
        if (children && children.classList.contains('tree-children')) {
          if (expanded) {
            children.style.display = 'none';
            toggle.setAttribute('data-expanded', 'false');
            toggle.innerHTML = '<i class="bi bi-chevron-right"></i>';
            var icon = node.querySelector('.tree-icon');
            if (icon) {
              icon.className = 'bi bi-folder2 tree-icon text-muted';
            }
          } else {
            children.style.display = '';
            toggle.setAttribute('data-expanded', 'true');
            toggle.innerHTML = '<i class="bi bi-chevron-down"></i>';
            var icon = node.querySelector('.tree-icon');
            if (icon) {
              icon.className = 'bi bi-folder2-open tree-icon text-primary';
            }
          }
        }
        return;
      }

      var node = e.target.closest('.tree-node');
      if (node) {
        var allNodes = treeNav.querySelectorAll('.tree-node');
        allNodes.forEach(function (n) { n.classList.remove('active'); });
        node.classList.add('active');

        var sectionId = node.getAttribute('data-section');
        var sectionRow = document.querySelector('tr[data-section="' + sectionId + '"].section-header-row, tr[data-section="' + sectionId + '"].subsection-header-row');
        if (sectionRow && sectionRow.style.display !== 'none') {
          sectionRow.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        showSectionDetail(sectionId);
        if (narrowQuery.matches) setPanel('tree', false);
      }
    });
  }

  var narrowQuery = window.matchMedia('(max-width: 991.98px)');
  var panelBackdrop = document.getElementById('panelBackdrop');
  var panelOpen = { tree: true, details: false };
  var sheetOpen = null;

  function panelElement(name) {
    return document.getElementById('panel' + name.charAt(0).toUpperCase() + name.slice(1));
  }

  function isPanelOpen(name) {
    return narrowQuery.matches ? sheetOpen === name : panelOpen[name];
  }

  function applyPanels() {
    ['tree', 'details'].forEach(function (name) {
      var el = panelElement(name);
      if (!el) return;
      if (narrowQuery.matches) {
        el.classList.remove('collapsed');
        el.classList.toggle('show-mobile', sheetOpen === name);
      } else {
        el.classList.remove('show-mobile');
        el.classList.toggle('collapsed', !panelOpen[name]);
      }
    });
    if (panelBackdrop) panelBackdrop.classList.toggle('show', narrowQuery.matches && sheetOpen !== null);
    document.querySelectorAll('.project-panel-toggle').forEach(function (btn) {
      btn.setAttribute('aria-pressed', isPanelOpen(btn.getAttribute('data-panel')) ? 'true' : 'false');
    });
  }

  function setPanel(name, open) {
    if (narrowQuery.matches) {
      if (open) sheetOpen = name;
      else if (sheetOpen === name) sheetOpen = null;
    } else {
      panelOpen[name] = open;
    }
    applyPanels();
  }

  document.querySelectorAll('.project-panel-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-panel');
      setPanel(name, !isPanelOpen(name));
    });
  });

  document.querySelectorAll('[data-collapse]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      setPanel(btn.getAttribute('data-collapse'), false);
    });
  });

  if (panelBackdrop) {
    panelBackdrop.addEventListener('click', function () {
      sheetOpen = null;
      applyPanels();
    });
  }

  if (narrowQuery.addEventListener) narrowQuery.addEventListener('change', applyPanels);

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || e.defaultPrevented || !narrowQuery.matches || !sheetOpen) return;
    if (document.querySelector('.modal.show')) return;
    sheetOpen = null;
    applyPanels();
  });

  applyPanels();

  function initResize(handleId, leftPanelId, direction) {
    var handle = document.getElementById(handleId);
    if (!handle) return;
    var panel = document.getElementById(leftPanelId);
    if (!panel) return;
    var startX, startWidth;

    handle.addEventListener('mousedown', function (e) {
      startX = e.clientX;
      startWidth = panel.offsetWidth;
      handle.classList.add('active');
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      e.preventDefault();
    });

    function onMouseMove(e) {
      var diff = e.clientX - startX;
      if (direction === 'right') diff = -diff;
      var newWidth = Math.max(180, Math.min(startWidth + diff, 500));
      panel.style.width = newWidth + 'px';
      panel.style.minWidth = newWidth + 'px';
      panel.style.maxWidth = newWidth + 'px';
    }

    function onMouseUp() {
      handle.classList.remove('active');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      try { localStorage.setItem('sd_panel_' + leftPanelId, panel.style.width); } catch (e) {}
    }
  }

  function restorePanelWidth(panelId) {
    var saved = null;
    try { saved = localStorage.getItem('sd_panel_' + panelId); } catch (e) {}
    if (saved) {
      var panel = document.getElementById(panelId);
      if (panel) {
        panel.style.width = saved;
        panel.style.minWidth = saved;
        panel.style.maxWidth = saved;
      }
    }
  }
  restorePanelWidth('panelTree');
  restorePanelWidth('panelDetails');

  initResize('resizeTree', 'panelTree', 'left');
  initResize('resizeDetails', 'panelDetails', 'right');

  var itemsTable = document.getElementById('itemsTable');
  var pendingDetailsOpen = null;

  function cancelPendingDetailsOpen() {
    if (pendingDetailsOpen) {
      clearTimeout(pendingDetailsOpen);
      pendingDetailsOpen = null;
    }
  }

  if (itemsTable) {
    itemsTable.addEventListener('click', function (e) {
      var row = e.target.closest('tr.item-row');
      if (!row) return;
      if (row.classList.contains('section-header-row') || row.classList.contains('subsection-header-row')) return;
      if (e.target.closest('.inline-edit-input, .col-actions, .drag-handle')) return;
      cancelPendingDetailsOpen();
      var editableTarget = isEditor && e.target.closest('.cell-editable');
      if (e.detail > 1) return;

      selectItem(row);
      if (isPanelOpen('details')) return;
      if (editableTarget) {
        pendingDetailsOpen = setTimeout(function () {
          pendingDetailsOpen = null;
          setPanel('details', true);
        }, 250);
      } else {
        setPanel('details', true);
      }
    });
  }

  function selectItem(row) {
    if (selectedItemRow) {
      selectedItemRow.classList.remove('selected');
    }
    row.classList.add('selected');
    selectedItemRow = row;
    selectedItemPk = parseInt(row.getAttribute('data-id'));
    selectedItemKey = row.getAttribute('data-key');

    clearReplyState();
    loadItemDetail(selectedItemKey);
  }

  function showSectionDetail(sectionId) {
    var sectionPanel = document.getElementById('sectionDetailsContent');
    var itemPanel = document.getElementById('detailsContent');
    var empty = document.getElementById('detailsEmpty');
    if (!sectionPanel) return;

    var data = window.SECTION_DATA && window.SECTION_DATA[sectionId];
    if (!data) return;

    document.getElementById('sectionDetailTitle').textContent = data.number + ' ' + data.title;
    document.getElementById('sectionDetailNumber').textContent = data.number;
    var countEl = document.getElementById('sectionDetailCount');
    if (countEl) {
      var count = data.total_items || 0;
      countEl.textContent = count === 0 ? gettext('No items') : interpolate(ngettext('%(count)s item', '%(count)s items', count), { count: count }, true);
    }
    var sectionAddBtn = document.getElementById('sectionAddItemBtn');
    if (sectionAddBtn) sectionAddBtn.setAttribute('data-section', data.key || '');
    var descEl = document.getElementById('sectionDetailDescription');
    descEl.textContent = data.description || gettext('No description');
    if (!data.description) {
      descEl.classList.add('fst-italic');
    } else {
      descEl.classList.remove('fst-italic');
    }

    if (itemPanel) itemPanel.classList.add('d-none');
    if (empty) empty.classList.add('d-none');
    sectionPanel.classList.remove('d-none');

    if (selectedItemRow) {
      selectedItemRow.classList.remove('selected');
      selectedItemRow = null;
      selectedItemPk = null;
      selectedItemKey = null;
    }
  }

  function loadItemDetail(key) {
    var content = document.getElementById('detailsContent');
    var empty = document.getElementById('detailsEmpty');
    var sectionPanel = document.getElementById('sectionDetailsContent');
    if (!content || !empty) return;

    fetchApi(apiUrl('items/' + key + '/')).then(function (r) {
      return r.json();
    }).then(function (data) {
      empty.classList.add('d-none');
      if (sectionPanel) sectionPanel.classList.add('d-none');
      content.classList.remove('d-none');
      renderItemDetail(data);
    });
  }

  function renderItemDetail(data) {
    var el = function (id) { return document.getElementById(id); };
    el('detailItemId').textContent = data.item_id;
    el('detailText').innerHTML = data.text || '';
    el('detailSection').textContent = data.section_number + ' ' + (data.section_title || '');
    el('detailCreated').textContent = formatDate(data.created_at);
    el('detailUpdated').textContent = formatDate(data.updated_at);

    el('detailStatus').innerHTML = statusBadge(data.status);
    el('detailPriority').innerHTML = priorityBadge(data.priority);
    if (data.assignee_name) {
      el('detailAssignee').innerHTML = '<span class="avatar-xs" style="background:' + escapeHtml(data.assignee_color) + '">' + escapeHtml(data.assignee_initials) + '</span> <span class="small">' + escapeHtml(data.assignee_name) + '</span>';
    } else {
      el('detailAssignee').innerHTML = '<span class="small text-muted">' + gettext('Unassigned') + '</span>';
    }

    var imageSection = el('detailImageSection');
    if (imageSection) {
      if (data.image) {
        imageSection.classList.remove('d-none');
        var img = el('detailImage');
        if (img) {
          img.src = data.image;
          img.onclick = function () { window.open(data.image, '_blank'); };
        }
        var caption = el('detailImageCaption');
        if (caption) caption.textContent = data.image_caption || '';
      } else {
        imageSection.classList.add('d-none');
      }
    }

    var attrContainer = el('detailCustomAttributes');
    if (attrContainer) {
      attrContainer.innerHTML = '';
      if (data.attribute_values && data.attribute_values.length > 0) {
        data.attribute_values.forEach(function (av) {
          var displayVal = av.display_value != null ? av.display_value : av.value;
          if (av.attribute_type === 'multiselect' && displayVal) {
            displayVal = displayVal.split(',').map(function (v) {
              return '<span class="badge bg-secondary bg-opacity-10 text-secondary me-1">' + escapeHtml(v.trim()) + '</span>';
            }).join('');
          } else {
            displayVal = escapeHtml(displayVal);
          }
          attrContainer.innerHTML += '<div class="details-attr-row"><span class="details-attr-label">' + escapeHtml(av.attribute_name) + '</span><span class="small">' + displayVal + '</span></div>';
        });
      }
    }

    renderDetailTags(data.tags || []);

    renderDetailAttachments(data.attachments || []);

    renderDetailLinks(data.outgoing_links || [], data.incoming_links || []);

    renderDetailComments(data.comments || []);

    renderDetailHistory(data.item_id);
  }

  function renderDetailTags(tags) {
    var container = document.getElementById('detailsTagsList');
    if (!container) return;
    if (tags.length === 0) {
      container.innerHTML = '<span class="text-muted small">' + gettext('No tags') + '</span>';
      return;
    }
    container.innerHTML = tags.map(function (t) {
      return '<span class="badge me-1" data-tag-id="' + escapeHtml(String(t.id)) + '" style="background-color:' + escapeHtml(t.color) + '20;color:' + escapeHtml(t.color) + '">' + escapeHtml(t.name) + '</span>';
    }).join('');
  }

  function renderDetailAttachments(attachments) {
    var container = document.getElementById('detailsAttachmentsList');
    var countEl = document.getElementById('attachmentsCount');
    if (countEl) countEl.textContent = attachments.length;
    if (!container) return;
    if (attachments.length === 0) {
      container.innerHTML = '<span class="text-muted small">' + gettext('No attachments') + '</span>';
      return;
    }
    var downloadBase = '/projects/' + projectSlug + '/attachments/';
    container.innerHTML = attachments.map(function (a) {
      return '<div class="d-flex align-items-center gap-2 mb-1">' +
        '<i class="bi ' + escapeHtml(a.file_type_icon) + '"></i>' +
        '<a href="' + downloadBase + a.public_key + '/download/" target="_blank" class="small text-decoration-none" title="' + gettext('Download') + '">' + escapeHtml(a.filename) + '</a>' +
        '<span class="small text-muted ms-auto">' + escapeHtml(a.file_size_display) + '</span>' +
        (isEditor ? '<button class="btn btn-sm btn-link text-danger p-0 delete-attachment-btn" data-id="' + a.public_key + '" title="' + gettext('Delete') + '"><i class="bi bi-x-lg"></i></button>' : '') +
        '</div>';
    }).join('');
  }

  function renderDetailLinks(outgoing, incoming) {
    var container = document.getElementById('detailsLinksList');
    if (!container) return;
    var all = outgoing.concat(incoming);
    if (all.length === 0) {
      container.innerHTML = '<span class="text-muted small">' + gettext('No links') + '</span>';
      return;
    }
    function linkRow(link, label, itemId, note) {
      return '<div class="d-flex align-items-center gap-2 mb-1">' +
        '<span class="small fw-medium text-nowrap">' + escapeHtml(label) + '</span>' +
        '<span class="small text-primary text-nowrap">' + escapeHtml(itemId) + '</span>' +
        '<span class="small text-muted">(' + escapeHtml(note) + ')</span>' +
        (isEditor ? '<button class="btn btn-sm btn-link text-danger p-0 ms-auto delete-link-btn" data-id="' + link.public_key + '" title="' + gettext('Remove') + '"><i class="bi bi-x-lg"></i></button>' : '') +
        '</div>';
    }
    container.innerHTML = outgoing.map(function (l) {
      return linkRow(l, l.link_type_display, l.target_item_id, l.target_project_name || '');
    }).concat(incoming.map(function (l) {
      return linkRow(l, gettext('From'), l.source_item_id, l.link_type_display + ', ' + (l.source_project_name || ''));
    })).join('');
  }

  function renderDetailComments(comments) {
    var container = document.getElementById('commentsList');
    var countEl = document.getElementById('commentsCount');
    if (countEl) countEl.textContent = comments.length;
    if (!container) return;
    if (comments.length === 0) {
      container.innerHTML = '<span class="text-muted small">' + gettext('No comments yet') + '</span>';
      return;
    }
    var topLevel = [];
    var replies = {};
    comments.forEach(function (c) {
      if (c.parent) {
        if (!replies[c.parent]) replies[c.parent] = [];
        replies[c.parent].push(c);
      } else {
        topLevel.push(c);
      }
    });

    function renderComment(c, isReply) {
      var actions = '';
      if (!isArchived) {
        actions += '<button class="btn btn-sm btn-light border-0 comment-reply-btn" data-id="' + c.id + '" data-author="' + escapeHtml(c.author_name) + '" title="' + gettext('Reply') + '"><i class="bi bi-reply"></i></button>';
      }
      if (!isArchived && (c.author === currentUserId || isAdmin)) {
        actions += '<button class="btn btn-sm btn-light border-0 comment-delete-btn" data-id="' + c.public_key + '" title="' + gettext('Delete') + '"><i class="bi bi-trash"></i></button>';
      }
      var html = '<div class="details-comment' + (isReply ? ' ms-4 ps-2 border-start' : '') + '" data-comment-id="' + c.id + '">' +
        '<div class="d-flex align-items-center gap-2 mb-1">' +
          '<span class="avatar-xs" style="background:' + escapeHtml(c.author_color) + '">' + escapeHtml(c.author_initials) + '</span>' +
          '<span class="small fw-semibold">' + escapeHtml(c.author_name) + '</span>' +
          '<span class="small text-muted ms-auto">' + formatDate(c.created_at) + '</span>' +
          '<div class="details-comment-actions">' + actions + '</div>' +
        '</div>' +
        '<div class="small">' + escapeHtml(c.text) + '</div>' +
      '</div>';
      if (replies[c.id]) {
        replies[c.id].forEach(function (r) {
          html += renderComment(r, true);
        });
      }
      return html;
    }

    container.innerHTML = topLevel.map(function (c) {
      return renderComment(c, false);
    }).join('');
  }

  function renderDetailHistory(itemId) {
    var container = document.getElementById('detailHistory');
    if (!container) return;
    container.innerHTML = '<span class="text-muted small">' + gettext('Loading...') + '</span>';
    fetchApi(apiUrl('audit-log/?target_id=' + encodeURIComponent(itemId) + '&limit=10')).then(function (r) {
      return r.json();
    }).then(function (data) {
      var entries = data.results || [];
      if (entries.length === 0) {
        container.innerHTML = '<span class="text-muted small">' + gettext('No history') + '</span>';
        return;
      }
      container.innerHTML = entries.map(function (e) {
        var icon = e.icon || 'bi-circle';
        var iconColor = e.icon_color || 'text-muted';
        var desc = escapeHtml(e.action_display);
        if (e.details) {
          if (e.details.old_status && e.details.new_status) {
            desc = escapeHtml(interpolate(gettext('Status: %(from)s → %(to)s'), { from: e.details.old_status, to: e.details.new_status }, true));
          } else if (e.details.old_priority && e.details.new_priority) {
            desc = escapeHtml(interpolate(gettext('Priority: %(from)s → %(to)s'), { from: e.details.old_priority, to: e.details.new_priority }, true));
          } else if (e.details.tags) {
            desc = escapeHtml(e.action_display) + ': ' + e.details.tags.map(escapeHtml).join(', ');
          } else if (e.details.filename) {
            desc = escapeHtml(e.action_display) + ': ' + escapeHtml(e.details.filename);
          } else if (e.details.target) {
            desc = escapeHtml(e.action_display) + ': ' + escapeHtml(e.details.target);
          } else if (e.details.text) {
            desc = escapeHtml(e.action_display) + ': ' + escapeHtml(stripHtml(e.details.text));
          }
        }
        return '<div class="d-flex align-items-start gap-2 mb-2">' +
          '<i class="bi ' + icon + ' ' + iconColor + ' mt-1"></i>' +
          '<div class="small">' +
            '<div>' + desc + '</div>' +
            '<div class="text-muted">' + escapeHtml(e.user_name) + ' · ' + formatDate(e.created_at) + '</div>' +
          '</div>' +
        '</div>';
      }).join('');
    }).catch(function () {
      container.innerHTML = '<span class="text-muted small">' + gettext('Failed to load history') + '</span>';
    });
  }

  if (itemsTable && isEditor) {
    itemsTable.addEventListener('dblclick', function (e) {
      cancelPendingDetailsOpen();
      var cell = e.target.closest('.cell-editable');
      if (!cell) return;
      var row = cell.closest('tr.item-row');
      if (!row || row.classList.contains('section-header-row') || row.classList.contains('subsection-header-row')) return;

      var field = cell.getAttribute('data-field');
      var itemKey = row.getAttribute('data-key');
      startInlineEdit(cell, field, itemKey);
    });
  }

  function startInlineEdit(cell, field, itemKey) {
    if (field === 'text') {
      fetchApi(apiUrl('items/' + itemKey + '/')).then(function (r) {
        return r.json();
      }).then(function (data) {
        if (data.text && hasComplexHtml(data.text)) {
          var row = cell.closest('tr.item-row');
          if (row) selectItem(row);
          var editBtn = document.getElementById('detailEditBtn');
          if (editBtn) editBtn.click();
        } else {
          _doInlineEdit(cell, field, itemKey);
        }
      });
      return;
    }
    _doInlineEdit(cell, field, itemKey);
  }

  function _doInlineEdit(cell, field, itemKey) {
    if (cell.querySelector('.inline-edit-input')) return;
    var currentText = cell.textContent.trim();
    var input;

    if (field === 'status') {
      input = document.createElement('select');
      input.className = 'form-select form-select-sm inline-edit-input';
      var statusOptionLabels = { draft: gettext('Draft'), 'in-review': gettext('In review'), approved: gettext('Approved'), rejected: gettext('Rejected') };
      ['draft', 'in-review', 'approved', 'rejected'].forEach(function (s) {
        var opt = document.createElement('option');
        opt.value = s;
        opt.textContent = statusOptionLabels[s];
        input.appendChild(opt);
      });
      var row = cell.closest('tr');
      input.value = row.getAttribute('data-status') || 'draft';
    } else if (field === 'priority') {
      input = document.createElement('select');
      input.className = 'form-select form-select-sm inline-edit-input';
      ['high', 'medium', 'low'].forEach(function (p) {
        var opt = document.createElement('option');
        opt.value = p;
        opt.textContent = PRIORITY_LABELS[p];
        input.appendChild(opt);
      });
      var row = cell.closest('tr');
      input.value = row.getAttribute('data-priority') || 'medium';
    } else {
      input = document.createElement('input');
      input.type = 'text';
      input.className = 'form-control form-control-sm inline-edit-input';
      input.value = currentText;
    }

    var originalHTML = cell.innerHTML;
    cell.innerHTML = '';
    cell.appendChild(input);
    input.focus();

    function save() {
      var newValue = input.value;
      if (field === 'text' && newValue && !/^\s*</.test(newValue)) {
        newValue = '<p>' + newValue + '</p>';
      }
      fetchApi(apiUrl('items/' + itemKey + '/inline-edit/'), {
        method: 'PATCH',
        body: JSON.stringify({ field: field, value: newValue }),
      }).then(function (r) {
        if (r.ok) return r.json();
        throw new Error('Save failed');
      }).then(function (data) {
        var row = cell.closest('tr');
        if (field === 'status') {
          row.setAttribute('data-status', data.status);
          cell.innerHTML = statusBadge(data.status);
        } else if (field === 'priority') {
          row.setAttribute('data-priority', data.priority);
          cell.innerHTML = priorityBadge(data.priority);
        } else if (field === 'text') {
          cell.innerHTML = '';
          if (data.image) {
            var div = document.createElement('div');
            div.className = 'mb-1';
            var img = document.createElement('img');
            img.src = data.image;
            img.className = 'img-fluid rounded border';
            img.style.maxHeight = '120px';
            img.alt = data.image_caption || '';
            div.appendChild(img);
            if (data.image_caption) {
              var cap = document.createElement('div');
              cap.className = 'text-muted small';
              cap.textContent = data.image_caption;
              div.appendChild(cap);
            }
            cell.appendChild(div);
          }
          cell.appendChild(document.createTextNode(stripHtml(data.text)));
        }
        if (selectedItemKey === itemKey) {
          loadItemDetail(itemKey);
        }
      }).catch(function () {
        cell.innerHTML = originalHTML;
        window.showToast(gettext('Failed to save changes'), 'danger');
      });
    }

    input.addEventListener('blur', save);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') { cell.innerHTML = originalHTML; }
    });
  }

  var itemMenu = document.getElementById('itemMenu');
  var contextItemRow = null;
  var contextItemKey = null;

  function sectionRows(row) {
    return Array.prototype.slice.call(itemsTable.querySelectorAll('tr.item-row[data-key][data-section="' + row.getAttribute('data-section') + '"]'));
  }

  function setMenuItemDisabled(item, disabled) {
    if (!item) return;
    if (disabled) item.setAttribute('aria-disabled', 'true');
    else item.removeAttribute('aria-disabled');
  }

  function setRadioChecks(menu, value) {
    Array.prototype.forEach.call(menu.querySelectorAll('[role="menuitemradio"]'), function (item) {
      item.setAttribute('aria-checked', item.getAttribute('data-value') === value ? 'true' : 'false');
    });
  }

  function setTagMenuChecks(menu, tagIds) {
    Array.prototype.forEach.call(menu.querySelectorAll('[data-action="set-tag"]'), function (item) {
      item.setAttribute('aria-checked', tagIds.indexOf(item.getAttribute('data-value')) !== -1 ? 'true' : 'false');
    });
  }

  function tagIdsIn(container) {
    return Array.prototype.map.call(container.querySelectorAll('[data-tag-id]'), function (badge) { return badge.getAttribute('data-tag-id'); });
  }

  function renderRowTags(row, items) {
    var cell = row.querySelector('.col-tags');
    if (!cell) return;
    cell.innerHTML = '';
    items.forEach(function (item) {
      var badge = document.createElement('span');
      badge.className = 'badge';
      badge.setAttribute('data-tag-id', item.getAttribute('data-value'));
      var color = item.getAttribute('data-tag-color');
      badge.style.backgroundColor = color + '20';
      badge.style.color = color;
      badge.textContent = item.getAttribute('data-tag-name');
      cell.appendChild(badge);
      cell.appendChild(document.createTextNode(' '));
    });
  }

  function applyTagMenu(menu, itemKey) {
    var items = Array.prototype.slice.call(menu.querySelectorAll('[data-action="set-tag"][aria-checked="true"]'));
    var tagIds = items.map(function (item) { return parseInt(item.getAttribute('data-value')); });
    return fetchApi(apiUrl('items/' + itemKey + '/tags/'), {
      method: 'PUT',
      body: JSON.stringify({ tag_ids: tagIds }),
    }).then(function (r) {
      if (!r.ok) throw new Error('Tags not saved');
      var row = itemsTable ? itemsTable.querySelector('tr.item-row[data-key="' + itemKey + '"]') : null;
      if (row) renderRowTags(row, items);
      if (selectedItemKey === itemKey) loadItemDetail(itemKey);
      window.showToast(gettext('Tags updated'), 'success', { id: 'tags-updated' });
    }).catch(function () {
      window.showToast(gettext('Tags could not be saved'), 'danger', { id: 'tags-updated' });
    });
  }

  var STATUS_ORDER = ['draft', 'in-review', 'approved', 'rejected'];
  var STATUS_LABELS = { draft: gettext('Draft'), 'in-review': gettext('In Review'), approved: gettext('Approved'), rejected: gettext('Rejected') };
  var PRIORITY_ORDER = ['high', 'medium', 'low'];
  var PRIORITY_LABELS = { high: gettext('High'), medium: gettext('Medium'), low: gettext('Low') };

  function orderedKeys(counts, order) {
    return order.filter(function (key) { return counts[key]; }).concat(Object.keys(counts).filter(function (key) {
      return order.indexOf(key) === -1;
    }));
  }

  function refreshStatusFooter() {
    var progress = document.getElementById('statusProgress');
    var summary = document.getElementById('statusSummary');
    if (!progress || !summary || !itemsTable) return;
    var counts = {};
    var total = 0;
    Array.prototype.forEach.call(itemsTable.querySelectorAll('tr.item-row[data-key]'), function (row) {
      var status = row.getAttribute('data-status') || 'draft';
      counts[status] = (counts[status] || 0) + 1;
      total++;
    });
    progress.innerHTML = '';
    summary.innerHTML = '';
    orderedKeys(counts, STATUS_ORDER).forEach(function (status) {
      var label = STATUS_LABELS[status] || status;
      var fill = STATUS_LABELS[status] ? 'status-fill-' + status : 'status-fill-other';
      var segment = document.createElement('div');
      segment.className = 'status-progress-segment ' + fill;
      segment.style.width = (total ? Math.round(counts[status] / total * 100) : 0) + '%';
      segment.title = counts[status] + ' ' + label;
      progress.appendChild(segment);
      var entry = document.createElement('span');
      entry.className = 'status-summary-item';
      var dot = document.createElement('span');
      dot.className = 'status-dot ' + fill;
      entry.appendChild(dot);
      entry.appendChild(document.createTextNode(counts[status] + ' ' + label));
      summary.appendChild(entry);
    });
  }

  function setItemField(itemKey, field, value) {
    return fetchApi(apiUrl('items/' + itemKey + '/inline-edit/'), {
      method: 'PATCH',
      body: JSON.stringify({ field: field, value: value }),
    }).then(function (r) {
      if (!r.ok) throw new Error('Not saved');
      return r.json();
    }).then(function (data) {
      var row = itemsTable ? itemsTable.querySelector('tr.item-row[data-key="' + itemKey + '"]') : null;
      if (row) {
        row.setAttribute('data-' + field, data[field]);
        var cell = row.querySelector('.col-' + field);
        if (cell) {
          var indicators = cell.querySelector('.item-indicators');
          cell.innerHTML = field === 'status' ? statusBadge(data.status) : priorityBadge(data.priority);
          if (indicators) {
            cell.appendChild(document.createElement('br'));
            cell.appendChild(indicators);
          }
        }
      }
      if (field === 'status') refreshStatusFooter();
      if (selectedItemKey === itemKey) loadItemDetail(itemKey);
      window.showToast(field === 'status' ? gettext('Status updated') : gettext('Priority updated'), 'success', { id: 'item-field' });
    }).catch(function () {
      window.showToast(gettext('The change could not be saved'), 'danger', { id: 'item-field' });
    });
  }

  if (itemsTable && itemMenu && isEditor) {
    itemMenu.addEventListener('menu:open', function (e) {
      if (e.target !== itemMenu) return;
      var target = e.detail.target;
      var row = target && target.closest ? target.closest('tr.item-row[data-key]') : null;
      if (!row) row = selectedItemRow;
      if (!row) {
        e.preventDefault();
        return;
      }
      contextItemRow = row;
      contextItemKey = row.getAttribute('data-key');
      setRadioChecks(document.getElementById('itemMenuStatus'), row.getAttribute('data-status'));
      setRadioChecks(document.getElementById('itemMenuPriority'), row.getAttribute('data-priority'));
      setTagMenuChecks(document.getElementById('itemMenuTags'), tagIdsIn(row));
      var siblings = sectionRows(row);
      var index = siblings.indexOf(row);
      setMenuItemDisabled(itemMenu.querySelector('[data-action="move-up"]'), index <= 0);
      setMenuItemDisabled(itemMenu.querySelector('[data-action="move-down"]'), index >= siblings.length - 1);
    });

    itemMenu.addEventListener('menu:select', function (e) {
      var action = e.detail.action;
      var value = e.detail.value;
      var row = contextItemRow;
      var key = contextItemKey;
      if (!row || !key) return;
      var itemId = row.getAttribute('data-item-id');
      if (action === 'set-status') {
        setItemField(key, 'status', value);
      } else if (action === 'set-priority') {
        setItemField(key, 'priority', value);
      } else if (action === 'set-tag') {
        applyTagMenu(e.detail.submenu || e.target.closest('.menu'), key);
      } else if (action === 'delete') {
        window.Modal.open('delete_item', { project: projectSlug, item: key });
      } else if (action === 'duplicate') {
        window.showConfirmModal({
          title: gettext('Duplicate Item'),
          bodyText: interpolate(gettext('Duplicate %(id)s? A copy is added to the same section.'), { id: itemId }, true),
          confirmText: gettext('Duplicate'),
          confirmClass: 'btn-primary',
          onConfirm: function () { duplicateItem(key); }
        });
      } else if (action === 'copy-id') {
        navigator.clipboard.writeText(itemId).then(function () {
          window.showToast(interpolate(gettext('Copied: %(id)s'), { id: itemId }, true), 'success');
        }).catch(function () {
          window.showToast(gettext('The browser refused the clipboard write'), 'danger');
        });
      } else if (action === 'copy-link') {
        navigator.clipboard.writeText(window.location.origin + window.location.pathname + '#' + itemId).then(function () {
          window.showToast(gettext('Link copied'), 'success');
        }).catch(function () {
          window.showToast(gettext('The browser refused the clipboard write'), 'danger');
        });
      } else if (action === 'edit') {
        selectItem(row);
        var editBtn = document.getElementById('detailEditBtn');
        if (editBtn) editBtn.click();
      } else if (action === 'insert-above') {
        insertItem(row, 'above');
      } else if (action === 'insert-below') {
        insertItem(row, 'below');
      } else if (action === 'move-up') {
        moveItem(key, parseInt(row.getAttribute('data-id')), 'up');
      } else if (action === 'move-down') {
        moveItem(key, parseInt(row.getAttribute('data-id')), 'down');
      }
    });
  }

  var detailTagsMenu = document.getElementById('detailTagsMenu');
  if (detailTagsMenu && isEditor) {
    detailTagsMenu.addEventListener('menu:open', function (e) {
      if (!selectedItemKey) {
        e.preventDefault();
        return;
      }
      setTagMenuChecks(detailTagsMenu, tagIdsIn(document.getElementById('detailsTagsList')));
    });
    detailTagsMenu.addEventListener('menu:select', function (e) {
      if (e.detail.action === 'set-tag' && selectedItemKey) applyTagMenu(detailTagsMenu, selectedItemKey);
    });
  }

  function initModalSearchableSelects(modal) {
    var wrappers = modal.querySelectorAll('.searchable-select');
    for (var i = 0; i < wrappers.length; i++) initSearchableSelect(wrappers[i]);
  }

  function initAddItemModal(modal) {
    initModalSearchableSelects(modal);
    var submit = modal.querySelector('#addItemSubmit');
    if (!submit) return;
    submit.addEventListener('click', function () {
      var section = modal.querySelector('#addItemSection').value;
      var text = getTinyMCEContent('addItemText').trim();
      var status = modal.querySelector('#addItemStatus').value;
      var priority = modal.querySelector('#addItemPriority').value;
      if (!text || text === '<p></p>') return;
      var addPayload = { section: section, text: text, status: status, priority: priority };
      var addAssignee = modal.querySelector('#addItemAssignee');
      if (addAssignee && addAssignee.value) addPayload.assignee = parseInt(addAssignee.value);
      if (pendingInsert && pendingInsert.section === section) {
        addPayload[pendingInsert.position === 'above' ? 'insert_before' : 'insert_after'] = pendingInsert.key;
      }
      var attrVals = collectAttributeValues('addItemCustomAttributes');
      if (attrVals.length > 0) addPayload.attribute_values = attrVals;
      submit.disabled = true;

      fetchApi(apiUrl('items/'), {
        method: 'POST',
        body: JSON.stringify(addPayload),
      }).then(function (r) {
        if (!r.ok) { window.showToast(gettext('Failed to add item'), 'danger'); submit.disabled = false; return null; }
        return r.json();
      }).then(function (data) {
        if (!data) return null;
        var imageInput = modal.querySelector('#addItemImage');
        var imageFile = imageInput && imageInput.files[0];
        if (imageFile) {
          var fd = new FormData();
          fd.append('image', imageFile);
          var caption = modal.querySelector('#addItemImageCaption');
          if (caption && caption.value.trim()) fd.append('image_caption', caption.value.trim());
          return fetchApi(apiUrl('items/' + data.public_key + '/image/'), {
            method: 'POST',
            body: fd,
          }).then(function () { return data; });
        }
        return data;
      }).then(function (data) {
        if (!data) return;
        window.Modal.close('confirmed');
        window.location.reload();
      });
    });
  }

  function initDeleteItemModal(modal) {
    var confirmBtn = modal.querySelector('#deleteItemConfirm');
    if (!confirmBtn) return;
    confirmBtn.addEventListener('click', function () {
      var key = confirmBtn.getAttribute('data-item-key');
      if (!key) return;
      confirmBtn.disabled = true;
      fetchApi(apiUrl('items/' + key + '/'), {
        method: 'DELETE',
      }).then(function (r) {
        if (r.ok) {
          window.Modal.close('confirmed');
          window.location.reload();
        } else {
          confirmBtn.disabled = false;
          window.showToast(gettext('Failed to delete item'), 'danger');
        }
      });
    });
  }

  var editItemBtn = document.getElementById('detailEditBtn');
  if (editItemBtn) {
    editItemBtn.addEventListener('click', function () {
      if (!selectedItemKey) return;
      window.Modal.open('edit_item', { project: projectSlug, item: selectedItemKey });
    });
  }

  function initEditItemModal(modal) {
    initModalSearchableSelects(modal);
    var form = modal.querySelector('#editItemForm');
    var submit = modal.querySelector('#editItemSubmit');
    if (!form || !submit) return;
    submit.addEventListener('click', function () {
      var key = form.getAttribute('data-item-key');
      if (!key) return;
      var payload = {
        section: parseInt(modal.querySelector('#editItemSection').value),
        text: getTinyMCEContent('editItemText').trim(),
        status: modal.querySelector('#editItemStatus').value,
        priority: modal.querySelector('#editItemPriority').value,
      };
      var assignee = modal.querySelector('#editItemAssignee').value;
      payload.assignee = assignee ? parseInt(assignee) : null;
      if (!payload.text || payload.text === '<p></p>') return;

      var editCaption = modal.querySelector('#editItemImageCaption');
      if (editCaption) payload.image_caption = editCaption.value.trim();
      payload.attribute_values = collectAttributeValues('editItemCustomAttributes');
      submit.disabled = true;

      fetchApi(apiUrl('items/' + key + '/'), {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }).then(function (r) {
        if (!r.ok) { window.showToast(gettext('Failed to update item'), 'danger'); submit.disabled = false; return null; }
        return r.json();
      }).then(function (data) {
        if (!data) return null;
        var removeCheck = modal.querySelector('#editItemRemoveImage');
        var imageInput = modal.querySelector('#editItemImage');
        var newFile = imageInput && imageInput.files[0];

        if (removeCheck && removeCheck.checked && !newFile) {
          return fetchApi(apiUrl('items/' + key + '/image/'), { method: 'DELETE' }).then(function () { return data; });
        }
        if (newFile) {
          var fd = new FormData();
          fd.append('image', newFile);
          if (editCaption && editCaption.value.trim()) fd.append('image_caption', editCaption.value.trim());
          return fetchApi(apiUrl('items/' + key + '/image/'), { method: 'POST', body: fd }).then(function () { return data; });
        }
        return data;
      }).then(function (data) {
        if (!data) return;
        window.Modal.close('confirmed');
        window.location.reload();
      });
    });
  }

  document.addEventListener('modal:show', function (e) {
    if (!e.detail) return;
    if (e.detail.name === 'add_item') initTinyMCE('addItemText');
    if (e.detail.name === 'edit_item') initTinyMCE('editItemText');
  });

  document.addEventListener('modal:shown', function (e) {
    if (!e.detail) return;
    if (e.detail.name === 'add_item') initAddItemModal(e.target);
    if (e.detail.name === 'edit_item') initEditItemModal(e.target);
    if (e.detail.name === 'delete_item') initDeleteItemModal(e.target);
    if (e.detail.name === 'export') initExportModal(e.target);
    if (e.detail.name === 'manage_sections') initManageSectionsModal(e.target);
  });

  document.addEventListener('modal:hide', function (e) {
    if (!e.detail) return;
    if (e.detail.name === 'add_item') destroyTinyMCE('addItemText');
    if (e.detail.name === 'edit_item') destroyTinyMCE('editItemText');
  });

  var changeImageBtn = document.getElementById('changeImageBtn');
  if (changeImageBtn) {
    var _imageInput = document.createElement('input');
    _imageInput.type = 'file';
    _imageInput.accept = 'image/png,image/jpeg,image/gif,image/webp';
    _imageInput.style.display = 'none';
    document.body.appendChild(_imageInput);
    changeImageBtn.addEventListener('click', function () {
      if (!selectedItemPk) return;
      _imageInput.click();
    });
    _imageInput.addEventListener('change', function () {
      if (!_imageInput.files[0] || !selectedItemPk) return;
      var fd = new FormData();
      fd.append('image', _imageInput.files[0]);
      fetchApi(apiUrl('items/' + selectedItemKey + '/image/'), {
        method: 'POST',
        body: fd,
      }).then(function (r) {
        if (r.ok) { loadItemDetail(selectedItemKey); window.showToast(gettext('Image updated'), 'success'); }
        else { window.showToast(gettext('Failed to upload image'), 'danger'); }
        _imageInput.value = '';
      });
    });
  }
  var removeImageBtn = document.getElementById('removeImageBtn');
  if (removeImageBtn) {
    removeImageBtn.addEventListener('click', function () {
      if (!selectedItemKey) return;
      var key = selectedItemKey;
      window.showConfirmModal({
        title: gettext('Remove Image'),
        body: gettext('Are you sure you want to remove this image?'),
        confirmText: gettext('Remove'),
        onConfirm: function () {
          fetchApi(apiUrl('items/' + key + '/image/'), {
            method: 'DELETE',
          }).then(function (r) {
            if (r.ok) { loadItemDetail(key); window.showToast(gettext('Image removed'), 'success'); }
            else { window.showToast(gettext('Failed to remove image'), 'danger'); }
          });
        }
      });
    });
  }

  function duplicateItem(key) {
    fetchApi(apiUrl('items/' + key + '/')).then(function (r) {
      return r.json();
    }).then(function (data) {
      var dupPayload = {
        section: data.section,
        text: interpolate(gettext('%(text)s (Copy)'), { text: data.text }, true),
        status: data.status,
        priority: data.priority,
      };
      if (data.attribute_values && data.attribute_values.length > 0) {
        dupPayload.attribute_values = data.attribute_values.map(function (av) {
          return { attribute: av.attribute, value: av.value };
        });
      }
      return fetchApi(apiUrl('items/'), {
        method: 'POST',
        body: JSON.stringify(dupPayload),
      });
    }).then(function (r) {
      if (r.ok) {
        window.showToast(gettext('Item duplicated'), 'success');
        window.location.reload();
      }
    });
  }

  var pendingInsert = null;

  function insertItem(refRow, position) {
    pendingInsert = { key: refRow.getAttribute('data-key'), section: refRow.getAttribute('data-section'), position: position };
    window.Modal.open('add_item', { project: projectSlug, section: refRow.getAttribute('data-section-key') });
  }

  document.addEventListener('modal:hidden', function (e) {
    if (e.detail && e.detail.name === 'add_item') pendingInsert = null;
  });

  function moveItem(key, pk, direction) {
    var row = itemsTable.querySelector('tr.item-row[data-key="' + key + '"]');
    if (!row) return;
    var rows = Array.prototype.slice.call(itemsTable.querySelectorAll('tr.item-row[data-key][data-section="' + row.getAttribute('data-section') + '"]'));
    var index = rows.indexOf(row);
    var target = direction === 'up' ? index - 1 : index + 1;
    if (index === -1 || target < 0 || target >= rows.length) return;
    var neighbour = rows[target];
    rows[index] = neighbour;
    rows[target] = row;
    fetchApi(apiUrl('items/reorder/'), {
      method: 'POST',
      body: JSON.stringify({ items: rows.map(function (r, i) { return { id: parseInt(r.getAttribute('data-id')), order: i }; }) }),
    }).then(function (r) {
      if (!r.ok) throw new Error('Not moved');
      if (direction === 'up') neighbour.before(row);
      else neighbour.after(row);
      window.showToast(direction === 'up' ? gettext('Item moved up') : gettext('Item moved down'), 'success', { id: 'item-moved' });
    }).catch(function () {
      window.showToast(gettext('The item could not be moved'), 'danger', { id: 'item-moved' });
    });
  }

  if (itemsTable && isEditor) {
    var dragRow = null;
    itemsTable.addEventListener('dragstart', function (e) {
      var row = e.target.closest('tr.item-row');
      if (!row || row.classList.contains('section-header-row') || row.classList.contains('subsection-header-row')) {
        e.preventDefault();
        return;
      }
      dragRow = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });

    function clearRowDropIndicators() {
      var rows = itemsTable.querySelectorAll('tr.drag-over-above, tr.drag-over-below');
      for (var i = 0; i < rows.length; i++) {
        rows[i].classList.remove('drag-over-above', 'drag-over-below');
      }
    }

    itemsTable.addEventListener('dragover', function (e) {
      e.preventDefault();
      var row = e.target.closest('tr.item-row');
      if (!row || row === dragRow) return;
      clearRowDropIndicators();
      var rect = row.getBoundingClientRect();
      var midY = rect.top + rect.height / 2;
      if (e.clientY < midY) {
        row.classList.add('drag-over-above');
      } else {
        row.classList.add('drag-over-below');
      }
    });

    itemsTable.addEventListener('dragleave', function (e) {
      var row = e.target.closest('tr.item-row');
      if (row) row.classList.remove('drag-over-above', 'drag-over-below');
    });

    itemsTable.addEventListener('drop', function (e) {
      e.preventDefault();
      var targetRow = e.target.closest('tr.item-row');
      if (!targetRow || !dragRow || targetRow === dragRow) return;
      clearRowDropIndicators();

      var tbody = itemsTable.querySelector('tbody');
      var rect = targetRow.getBoundingClientRect();
      var midY = rect.top + rect.height / 2;
      if (e.clientY < midY) {
        tbody.insertBefore(dragRow, targetRow);
      } else {
        tbody.insertBefore(dragRow, targetRow.nextSibling);
      }

      saveTableOrder();
    });

    itemsTable.addEventListener('dragend', function () {
      if (dragRow) {
        dragRow.classList.remove('dragging');
        dragRow = null;
      }
      clearRowDropIndicators();
    });
  }

  function saveTableOrder() {
    var rows = itemsTable.querySelectorAll('tbody tr.item-row');
    var items = [];
    var sectionId = null;
    var sectionChanged = false;
    rows.forEach(function (row) {
      if (row.classList.contains('section-header-row') || row.classList.contains('subsection-header-row')) {
        sectionId = row.getAttribute('data-section');
        return;
      }
      var pk = parseInt(row.getAttribute('data-id'));
      if (!pk || !sectionId) return;
      if (row.getAttribute('data-section') !== sectionId) sectionChanged = true;
      items.push({ id: pk, order: items.length, section: parseInt(sectionId) });
    });
    fetchApi(apiUrl('items/reorder/'), {
      method: 'POST',
      body: JSON.stringify({ items: items }),
    }).then(function (r) {
      if (!r.ok) {
        window.showToast(gettext('The new order was not saved'), 'danger');
        return;
      }
      if (sectionChanged) window.location.reload();
    });
  }

  var postCommentBtn = document.getElementById('postCommentBtn');
  if (postCommentBtn) {
    postCommentBtn.addEventListener('click', function () {
      if (!selectedItemPk) return;
      var input = document.getElementById('commentInput');
      var text = input.value.trim();
      if (!text) return;

      var payload = { text: text };
      if (replyToCommentId) {
        payload.parent = replyToCommentId;
      }

      fetchApi(apiUrl('items/' + selectedItemKey + '/comments/'), {
        method: 'POST',
        body: JSON.stringify(payload),
      }).then(function (r) {
        if (r.ok) {
          input.value = '';
          clearReplyState();
          loadItemDetail(selectedItemKey);
          window.showToast(gettext('Comment added'), 'success');
        }
      });
    });
  }

  function clearReplyState() {
    replyToCommentId = null;
    var banner = document.getElementById('replyBanner');
    if (banner) banner.remove();
    var input = document.getElementById('commentInput');
    if (input) input.placeholder = gettext('Add a comment... (Shift+Enter for new line)');
  }

  document.addEventListener('click', function (e) {
    var replyBtn = e.target.closest('.comment-reply-btn');
    if (replyBtn) {
      replyToCommentId = parseInt(replyBtn.getAttribute('data-id'));
      var authorName = replyBtn.getAttribute('data-author') || '';
      var input = document.getElementById('commentInput');
      if (input) {
        input.placeholder = interpolate(gettext('Replying to %(name)s...'), { name: authorName }, true);
        input.focus();
      }
      var existing = document.getElementById('replyBanner');
      if (existing) existing.remove();
      var commentInput = document.querySelector('.details-comment-input');
      if (commentInput) {
        var banner = document.createElement('div');
        banner.id = 'replyBanner';
        banner.className = 'small text-muted d-flex align-items-center gap-1 mb-1';
        banner.innerHTML = '<i class="bi bi-reply"></i> ' + interpolate(gettext('Replying to %(name)s'), { name: '<strong>' + escapeHtml(authorName) + '</strong>' }, true) +
          '<button class="btn btn-sm btn-link text-muted p-0 ms-auto" id="cancelReplyBtn" title="' + gettext('Cancel reply') + '"><i class="bi bi-x-lg"></i></button>';
        commentInput.insertBefore(banner, commentInput.firstChild);
        banner.querySelector('#cancelReplyBtn').addEventListener('click', clearReplyState);
      }
      return;
    }
  });

  var commentInput = document.getElementById('commentInput');
  if (commentInput) {
    commentInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (postCommentBtn) postCommentBtn.click();
      }
    });
  }

  var attachUploadBtn = document.getElementById('attachUploadBtn');
  var attachFileInput = document.getElementById('attachFileInput');
  if (attachUploadBtn && attachFileInput) {
    attachUploadBtn.addEventListener('click', function () {
      attachFileInput.click();
    });
    attachFileInput.addEventListener('change', function () {
      if (!selectedItemPk || !attachFileInput.files.length) return;
      var formData = new FormData();
      formData.append('file', attachFileInput.files[0]);
      fetchApi(apiUrl('items/' + selectedItemKey + '/attachments/'), {
        method: 'POST',
        body: formData,
      }).then(function (r) {
        if (r.ok) {
          attachFileInput.value = '';
          loadItemDetail(selectedItemKey);
          window.showToast(gettext('File uploaded'), 'success');
        } else {
          r.json().then(function (err) {
            var msg = err.file ? err.file[0] || err.file : gettext('Upload failed');
            window.showToast(msg, 'danger');
          }).catch(function () {
            window.showToast(gettext('Upload failed'), 'danger');
          });
        }
      });
    });
  }

  document.addEventListener('click', function (e) {
    var delAttach = e.target.closest('.delete-attachment-btn');
    if (delAttach) {
      var attachId = delAttach.getAttribute('data-id');
      window.showConfirmModal({
        title: gettext('Delete Attachment'),
        body: gettext('Are you sure you want to delete this attachment?'),
        confirmText: gettext('Delete'),
        onConfirm: function () {
          fetchApi(apiUrl('attachments/' + attachId + '/'), { method: 'DELETE' }).then(function (r) {
            if (r.ok && selectedItemPk) loadItemDetail(selectedItemKey);
          });
        }
      });
      return;
    }

    var delLink = e.target.closest('.delete-link-btn');
    if (delLink) {
      var linkId = delLink.getAttribute('data-id');
      window.showConfirmModal({
        title: gettext('Remove Link'),
        body: gettext('Remove this traceability link?'),
        confirmText: gettext('Remove'),
        onConfirm: function () {
          fetchApi(apiUrl('links/' + linkId + '/'), { method: 'DELETE' }).then(function (r) {
            if (r.ok) {
              window.showToast(gettext('Link removed'), 'success');
              if (selectedItemPk) loadItemDetail(selectedItemKey);
            } else {
              window.showToast(gettext('Failed to remove link'), 'danger');
            }
          });
        }
      });
      return;
    }

    var delComment = e.target.closest('.comment-delete-btn');
    if (delComment) {
      var commentId = delComment.getAttribute('data-id');
      window.showConfirmModal({
        title: gettext('Delete Comment'),
        body: gettext('Are you sure you want to delete this comment?'),
        confirmText: gettext('Delete'),
        onConfirm: function () {
          fetchApi(apiUrl('comments/' + commentId + '/'), { method: 'DELETE' }).then(function (r) {
            if (r.ok && selectedItemPk) {
              loadItemDetail(selectedItemKey);
              window.showToast(gettext('Comment deleted'), 'success');
            }
          });
        }
      });
      return;
    }
  });

  var templateAttributes = (typeof TEMPLATE_ATTRIBUTES !== 'undefined') ? TEMPLATE_ATTRIBUTES : [];

  function initExportModal(modal) {
    var exportAttrsCheckbox = modal.querySelector('#exportAttrs');
    var exportAttrsList = modal.querySelector('#exportAttrsList');
    if (!exportAttrsCheckbox || !exportAttrsList || !exportAttrsList.children.length) return;
    exportAttrsCheckbox.addEventListener('change', function () {
      exportAttrsList.style.display = exportAttrsCheckbox.checked ? '' : 'none';
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && !e.target.closest('input, textarea, select')) {
      e.preventDefault();
      var itemSearch = document.getElementById('itemSearch');
      if (itemSearch) itemSearch.focus();
    }
  });

  var summaryToggle = document.getElementById('summaryToggleBtn');
  var summaryOverlay = document.getElementById('projectSummary');
  var closeSummary = document.getElementById('closeSummaryBtn');
  function setSummaryOpen(open) {
    if (!summaryOverlay) return;
    summaryOverlay.classList.toggle('d-none', !open);
    if (summaryToggle) summaryToggle.setAttribute('aria-pressed', open ? 'true' : 'false');
    if (open) loadProjectSummary();
  }

  if (summaryToggle && summaryOverlay) {
    summaryToggle.addEventListener('click', function () {
      setSummaryOpen(summaryOverlay.classList.contains('d-none'));
    });
  }
  if (closeSummary && summaryOverlay) {
    closeSummary.addEventListener('click', function () {
      setSummaryOpen(false);
    });
  }

  function summaryStat(value, label) {
    return '<div class="summary-stat-item"><div class="summary-stat-value">' + escapeHtml(String(value)) + '</div><div class="summary-stat-label">' + escapeHtml(label) + '</div></div>';
  }

  function loadProjectSummary() {
    var rows = itemsTable ? Array.prototype.slice.call(itemsTable.querySelectorAll('tbody tr.item-row[data-key]')) : [];
    var statusMap = {};
    var priorityMap = {};
    var sectionMap = {};
    var unassigned = 0;
    var total = rows.length;
    rows.forEach(function (r) {
      var s = r.getAttribute('data-status');
      var p = r.getAttribute('data-priority');
      var sec = r.getAttribute('data-section');
      statusMap[s] = (statusMap[s] || 0) + 1;
      priorityMap[p] = (priorityMap[p] || 0) + 1;
      sectionMap[sec] = (sectionMap[sec] || 0) + 1;
      if (!r.querySelector('.col-assignee .avatar-xs')) unassigned++;
    });

    renderBreakdown('summaryStatusChart', 'summaryStatusLegend', statusMap, STATUS_ORDER, STATUS_LABELS, 'status-fill-', total);
    renderBreakdown('summaryPriorityChart', 'summaryPriorityLegend', priorityMap, PRIORITY_ORDER, PRIORITY_LABELS, 'priority-fill-', total);

    var sections = itemsTable ? Array.prototype.map.call(itemsTable.querySelectorAll('tr.section-header-row, tr.subsection-header-row'), function (hdr) {
      var label = hdr.querySelector('.col-text strong');
      return {
        number: hdr.getAttribute('data-number') || '',
        title: label ? label.textContent : '',
        direct: sectionMap[hdr.getAttribute('data-section')] || 0,
      };
    }) : [];
    sections.forEach(function (s) {
      s.total = sections.reduce(function (sum, other) {
        return sum + (other.number === s.number || other.number.indexOf(s.number + '.') === 0 ? other.direct : 0);
      }, 0);
    });
    var emptySections = sections.filter(function (s) { return s.total === 0; }).length;
    var maxTotal = sections.reduce(function (max, s) { return Math.max(max, s.total); }, 0);

    var quickStats = document.getElementById('summaryQuickStats');
    if (quickStats) {
      var approved = statusMap.approved || 0;
      quickStats.innerHTML =
        summaryStat(total, ngettext('Item', 'Items', total)) +
        summaryStat(total ? Math.round(approved / total * 100) + '%' : '0%', interpolate(gettext('Approved (%(approved)s of %(total)s)'), { approved: approved, total: total }, true)) +
        summaryStat(unassigned, gettext('Unassigned')) +
        summaryStat(emptySections, interpolate(gettext('Sections without items (of %(count)s)'), { count: sections.length }, true));
    }

    var sectionList = document.getElementById('summarySectionList');
    if (sectionList) {
      sectionList.innerHTML = sections.map(function (s) {
        var depth = s.number.split('.').length - 1;
        var width = maxTotal ? Math.round(s.total / maxTotal * 100) : 0;
        return '<div class="summary-section-row' + (s.total ? '' : ' is-empty') + '">' +
          '<span class="summary-section-name" style="padding-left:' + depth + 'rem" title="' + escapeHtml(s.number + ' ' + s.title) + '">' + escapeHtml(s.number + ' ' + s.title) + '</span>' +
          '<span class="summary-section-bar-track"><span class="summary-section-bar-fill d-block" style="width:' + width + '%"></span></span>' +
          '<span class="summary-section-count">' + s.total + '</span>' +
          '</div>';
      }).join('') || '<span class="text-muted small">' + gettext('No sections') + '</span>';
    }

    var recentChanges = document.getElementById('summaryRecentChanges');
    if (recentChanges) {
      recentChanges.innerHTML = '<div class="text-center py-2"><div class="spinner-border spinner-border-sm"></div></div>';
      fetchApi(apiUrl('audit-log/?limit=8')).then(function (r) {
        return r.json();
      }).then(function (data) {
        var entries = data.results || [];
        if (entries.length === 0) {
          recentChanges.innerHTML = '<span class="text-muted small">' + gettext('No recent changes') + '</span>';
          return;
        }
        recentChanges.innerHTML = entries.map(function (e) {
          return '<div class="d-flex align-items-start gap-2 mb-2">' +
            '<span class="avatar-xs" style="background:' + escapeHtml(e.user_color) + '">' + escapeHtml(e.user_initials) + '</span>' +
            '<div class="flex-fill">' +
              '<div class="small"><strong>' + escapeHtml(e.user_name) + '</strong> ' + escapeHtml(e.action_display.toLowerCase()) + ' ' + escapeHtml(e.target_type.toLowerCase()) + ' <strong' + (e.target_type === 'Item' ? ' class="text-nowrap"' : '') + '>' + escapeHtml(e.target_id) + '</strong></div>' +
              '<div class="small text-muted">' + formatDate(e.created_at) + '</div>' +
            '</div>' +
          '</div>';
        }).join('');
      });
    }
  }

  function renderBreakdown(chartId, legendId, dataMap, order, labels, fillPrefix, total) {
    var chart = document.getElementById(chartId);
    var legend = document.getElementById(legendId);
    if (!chart || !legend) return;
    var keys = order.concat(Object.keys(dataMap).filter(function (key) { return order.indexOf(key) === -1; }));
    chart.innerHTML = keys.filter(function (key) { return dataMap[key]; }).map(function (key) {
      var label = labels[key] || key;
      var fill = labels[key] ? fillPrefix + key : 'status-fill-other';
      var pct = total > 0 ? dataMap[key] / total * 100 : 0;
      return '<div class="' + fill + '" style="width:' + pct + '%" title="' + escapeHtml(dataMap[key] + ' ' + label) + '"></div>';
    }).join('');
    legend.innerHTML = keys.map(function (key) {
      var count = dataMap[key] || 0;
      var label = labels[key] || key;
      var fill = labels[key] ? fillPrefix + key : 'status-fill-other';
      var pct = total > 0 ? Math.round(count / total * 100) : 0;
      return '<div class="summary-breakdown-row"><span class="status-dot ' + fill + '"></span>' + escapeHtml(label) +
        '<span class="summary-breakdown-count">' + count + '</span><span class="summary-breakdown-pct">' + pct + '%</span></div>';
    }).join('');
  }

  function statusBadge(status) {
    var map = {
      'draft': '<span class="status-pill status-draft">' + gettext('Draft') + '</span>',
      'in-review': '<span class="status-pill status-in-review">' + gettext('In Review') + '</span>',
      'approved': '<span class="status-pill status-approved">' + gettext('Approved') + '</span>',
      'rejected': '<span class="status-pill status-rejected">' + gettext('Rejected') + '</span>',
    };
    return map[status] || '<span class="status-pill status-other">' + escapeHtml(status) + '</span>';
  }

  function priorityBadge(priority) {
    var label = PRIORITY_LABELS[priority];
    var cls = label ? 'priority-' + priority : 'priority-other';
    return '<span class="priority-label ' + cls + '"><i class="bi bi-flag-fill" aria-hidden="true"></i>' + escapeHtml(label || priority) + '</span>';
  }

  function formatDate(isoString) {
    if (!isoString) return '';
    var d = new Date(isoString);
    var now = new Date();
    var diff = now - d;
    if (diff < 60000) return gettext('just now');
    if (diff < 3600000) return interpolate(gettext('%(count)sm ago'), { count: Math.floor(diff / 60000) }, true);
    if (diff < 86400000) return interpolate(gettext('%(count)sh ago'), { count: Math.floor(diff / 3600000) }, true);
    if (diff < 604800000) return interpolate(gettext('%(count)sd ago'), { count: Math.floor(diff / 86400000) }, true);
    var parts = {};
    new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric' }).formatToParts(d).forEach(function (p) { parts[p.type] = p.value; });
    return parts.day + ' ' + parts.month + ' ' + parts.year;
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function initSearchableSelect(wrapper) {
    var select = wrapper.querySelector('select');
    if (!select) return;

    var trigger = document.createElement('div');
    trigger.className = 'searchable-select-trigger';
    trigger.innerHTML = '<span class="ss-label"></span><i class="bi bi-chevron-down ss-arrow"></i>';
    wrapper.insertBefore(trigger, select);

    var dropdown = document.createElement('div');
    dropdown.className = 'searchable-select-dropdown';
    dropdown.innerHTML = '<div class="searchable-select-search"><input type="text" placeholder="' + gettext('Search...') + '" autocomplete="off"></div><div class="searchable-select-options"></div>';
    wrapper.appendChild(dropdown);

    var searchInput = dropdown.querySelector('input');
    var optionsContainer = dropdown.querySelector('.searchable-select-options');
    var labelSpan = trigger.querySelector('.ss-label');
    var highlightedIdx = -1;

    function getOptions() {
      var opts = [];
      for (var i = 0; i < select.options.length; i++) {
        var o = select.options[i];
        opts.push({
          value: o.value,
          text: o.textContent,
          color: o.getAttribute('data-color') || '',
          initials: o.getAttribute('data-initials') || ''
        });
      }
      return opts;
    }

    function renderLabel() {
      var opt = select.options[select.selectedIndex];
      if (!opt || !opt.value) {
        labelSpan.innerHTML = '<span class="text-muted">' + gettext('Unassigned') + '</span>';
        return;
      }
      var color = opt.getAttribute('data-color') || '#64748b';
      var ini = opt.getAttribute('data-initials') || '';
      var html = '';
      if (ini) {
        html += '<span class="avatar-xs" style="background:' + escapeHtml(color) + '">' + escapeHtml(ini) + '</span>';
      }
      html += escapeHtml(opt.textContent);
      labelSpan.innerHTML = html;
    }

    function renderOptions(filter) {
      var opts = getOptions();
      var lowerFilter = (filter || '').toLowerCase();
      var html = '';
      var count = 0;
      for (var i = 0; i < opts.length; i++) {
        if (lowerFilter && opts[i].text.toLowerCase().indexOf(lowerFilter) === -1) continue;
        var isSelected = opts[i].value === select.value;
        var cls = 'searchable-select-option' + (isSelected ? ' selected' : '');
        html += '<div class="' + cls + '" data-value="' + escapeHtml(opts[i].value) + '">';
        if (opts[i].initials) {
          var bg = opts[i].color || '#64748b';
          html += '<span class="avatar-xs" style="background:' + escapeHtml(bg) + '">' + escapeHtml(opts[i].initials) + '</span>';
        }
        html += escapeHtml(opts[i].text);
        html += '</div>';
        count++;
      }
      if (count === 0) {
        html = '<div class="searchable-select-no-results">' + gettext('No results') + '</div>';
      }
      optionsContainer.innerHTML = html;
      highlightedIdx = -1;
    }

    function setHighlight(idx) {
      var items = optionsContainer.querySelectorAll('.searchable-select-option');
      if (items.length === 0) return;
      for (var i = 0; i < items.length; i++) items[i].classList.remove('highlighted');
      if (idx < 0) idx = items.length - 1;
      if (idx >= items.length) idx = 0;
      highlightedIdx = idx;
      items[idx].classList.add('highlighted');
      items[idx].scrollIntoView({ block: 'nearest' });
    }

    function openDropdown() {
      wrapper.classList.add('open');
      searchInput.value = '';
      renderOptions('');
      setTimeout(function () { searchInput.focus(); }, 10);
    }

    function closeDropdown() {
      wrapper.classList.remove('open');
      highlightedIdx = -1;
    }

    function selectValue(val) {
      select.value = val;
      renderLabel();
      closeDropdown();
      var evt = new Event('change', { bubbles: true });
      select.dispatchEvent(evt);
    }

    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      if (wrapper.classList.contains('open')) {
        closeDropdown();
      } else {
        openDropdown();
      }
    });

    searchInput.addEventListener('input', function () {
      renderOptions(this.value);
    });

    searchInput.addEventListener('keydown', function (e) {
      var items = optionsContainer.querySelectorAll('.searchable-select-option');
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlight(highlightedIdx + 1);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlight(highlightedIdx - 1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (highlightedIdx >= 0 && items[highlightedIdx]) {
          selectValue(items[highlightedIdx].getAttribute('data-value'));
        }
      } else if (e.key === 'Escape') {
        closeDropdown();
      }
    });

    optionsContainer.addEventListener('click', function (e) {
      var option = e.target.closest('.searchable-select-option');
      if (option) {
        selectValue(option.getAttribute('data-value'));
      }
    });

    document.addEventListener('click', function (e) {
      if (!wrapper.contains(e.target)) {
        closeDropdown();
      }
    });

    renderLabel();
    wrapper._ssRefresh = renderLabel;
  }

  var ssWrappers = document.querySelectorAll('.searchable-select');
  for (var i = 0; i < ssWrappers.length; i++) {
    initSearchableSelect(ssWrappers[i]);
  }

  var BUILTIN_COLUMNS = [
    { key: 'tags', label: gettext('Tags'), cssClass: 'col-tags' },
    { key: 'assignee', label: gettext('Assignee'), cssClass: 'col-assignee' }
  ];
  var BASE_COLSPAN = isEditor ? 7 : 6;

  function initColumnVisibility() {
    var menu = document.getElementById('columnsMenu');
    if (!menu) return;

    var nonBuiltinAttrs = templateAttributes.filter(function (a) { return !a.is_builtin; });

    var visible = {};
    var builtinVisible = {};
    BUILTIN_COLUMNS.forEach(function (col) { builtinVisible[col.key] = true; });

    fetchApi(apiUrl('preferences/')).then(function (r) { return r.json(); }).then(function (data) {
      var prefs = data.preferences || {};
      visible = prefs.visible_columns || {};
      if (prefs.builtin_columns) {
        BUILTIN_COLUMNS.forEach(function (col) {
          if (typeof prefs.builtin_columns[col.key] !== 'undefined') {
            builtinVisible[col.key] = prefs.builtin_columns[col.key];
          }
        });
      }
      buildColumnCheckboxes();
      renderColumns();
    }).catch(function () {
      buildColumnCheckboxes();
      renderColumns();
    });

    function saveVisibleColumns() {
      fetchApi(apiUrl('preferences/'), {
        method: 'PATCH',
        body: JSON.stringify({ preferences: { visible_columns: visible, builtin_columns: builtinVisible } })
      });
    }

    function menuHeading(text) {
      var heading = document.createElement('div');
      heading.className = 'menu-heading';
      heading.setAttribute('role', 'presentation');
      heading.textContent = text;
      return heading;
    }

    function columnItem(kind, key, label, checked) {
      var item = document.createElement('button');
      item.type = 'button';
      item.className = 'menu-item';
      item.setAttribute('role', 'menuitemcheckbox');
      item.setAttribute('tabindex', '-1');
      item.setAttribute('aria-checked', checked ? 'true' : 'false');
      item.setAttribute('data-action', 'toggle-column');
      item.setAttribute('data-kind', kind);
      item.setAttribute('data-value', key);
      var text = document.createElement('span');
      text.className = 'menu-item-text';
      text.textContent = label;
      var check = document.createElement('i');
      check.className = 'bi bi-check-lg menu-item-check';
      check.setAttribute('aria-hidden', 'true');
      item.appendChild(text);
      item.appendChild(check);
      return item;
    }

    function buildColumnCheckboxes() {
      menu.innerHTML = '';
      menu.appendChild(menuHeading(gettext('Columns')));
      BUILTIN_COLUMNS.forEach(function (col) {
        menu.appendChild(columnItem('builtin', col.key, col.label, builtinVisible[col.key] !== false));
      });
      if (nonBuiltinAttrs.length > 0) {
        var separator = document.createElement('div');
        separator.className = 'menu-separator';
        separator.setAttribute('role', 'separator');
        menu.appendChild(separator);
        menu.appendChild(menuHeading(gettext('Custom Attributes')));
        nonBuiltinAttrs.forEach(function (attr) {
          menu.appendChild(columnItem('attr', String(attr.id), attr.name, !!visible[attr.id]));
        });
      }
    }

    menu.addEventListener('menu:select', function (e) {
      if (e.detail.action !== 'toggle-column') return;
      var item = e.detail.item;
      if (item.getAttribute('data-kind') === 'builtin') builtinVisible[item.getAttribute('data-value')] = e.detail.checked;
      else visible[item.getAttribute('data-value')] = e.detail.checked;
      saveVisibleColumns();
      renderColumns();
      window.Menu.reposition();
    });

    function renderColumns() {
      var table = document.getElementById('itemsTable');
      if (!table) return;

      BUILTIN_COLUMNS.forEach(function (col) {
        var show = builtinVisible[col.key] !== false;
        var els = table.querySelectorAll('.' + col.cssClass);
        for (var i = 0; i < els.length; i++) {
          els[i].style.display = show ? '' : 'none';
        }
      });

      var hiddenBuiltinCount = 0;
      BUILTIN_COLUMNS.forEach(function (col) {
        if (builtinVisible[col.key] === false) hiddenBuiltinCount++;
      });

      var existingTh = table.querySelectorAll('.col-attr');
      for (var i = 0; i < existingTh.length; i++) existingTh[i].remove();
      var existingTd = table.querySelectorAll('.td-attr');
      for (var j = 0; j < existingTd.length; j++) existingTd[j].remove();

      var visibleAttrs = nonBuiltinAttrs.filter(function (a) { return !!visible[a.id]; });

      var totalColspan = BASE_COLSPAN - hiddenBuiltinCount + visibleAttrs.length;

      var sectionHeaders = table.querySelectorAll('.section-header-row td[colspan], .subsection-header-row td[colspan]');
      for (var sh = 0; sh < sectionHeaders.length; sh++) sectionHeaders[sh].setAttribute('colspan', totalColspan);

      if (visibleAttrs.length === 0) return;

      var headerRow = table.querySelector('thead tr');
      var updatedTh = headerRow.querySelector('.col-updated');
      visibleAttrs.forEach(function (attr) {
        var th = document.createElement('th');
        th.className = 'col-attr';
        th.style.minWidth = '120px';
        th.style.whiteSpace = 'nowrap';
        th.textContent = attr.name;
        headerRow.insertBefore(th, updatedTh);
      });

      var rows = table.querySelectorAll('tbody tr');
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        if (row.classList.contains('section-header-row') || row.classList.contains('subsection-header-row')) continue;
        var itemPk = row.getAttribute('data-id');
        var updatedTd = row.querySelector('.col-updated');
        if (!updatedTd) continue;
        visibleAttrs.forEach(function (attr) {
          var td = document.createElement('td');
          td.className = 'td-attr';
          td.style.minWidth = '120px';
          td.style.overflow = 'hidden';
          td.style.textOverflow = 'ellipsis';
          td.style.whiteSpace = 'nowrap';
          td.innerHTML = '<span class="small text-muted" data-item="' + itemPk + '" data-attr="' + attr.id + '"></span>';
          row.insertBefore(td, updatedTd);
        });
      }

      fetchAllPages('items/').then(function (items) {
        items.forEach(function (item) {
          if (!item.attribute_values) return;
          item.attribute_values.forEach(function (av) {
            var cell = table.querySelector('span[data-item="' + item.id + '"][data-attr="' + av.attribute + '"]');
            if (cell) {
              var displayVal = av.display_value != null ? av.display_value : av.value;
              cell.textContent = displayVal;
              cell.title = displayVal;
            }
          });
        });
      });
    }
  }

  initColumnVisibility();

  function selectItemFromHash() {
    if (!itemsTable || location.hash.length < 2) return;
    var itemId = decodeURIComponent(location.hash.slice(1));
    var row = itemsTable.querySelector('tr.item-row[data-item-id="' + CSS.escape(itemId) + '"]');
    if (!row) return;
    selectItem(row);
    setPanel('details', true);
    row.scrollIntoView({ block: 'center' });
  }

  window.addEventListener('hashchange', selectItemFromHash);
  selectItemFromHash();

  function collectAttributeValues(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return [];
    var inputs = container.querySelectorAll('.attr-input');
    var result = [];
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      var attrId = parseInt(input.getAttribute('data-attr-id'));
      var val = '';
      if (input.getAttribute('data-type') === 'boolean') {
        val = input.checked ? 'true' : 'false';
      } else if (input.getAttribute('data-type') === 'multiselect') {
        var selected = [];
        for (var j = 0; j < input.options.length; j++) {
          if (input.options[j].selected) selected.push(input.options[j].value);
        }
        val = selected.join(', ');
      } else {
        val = input.value;
      }
      if (val) {
        result.push({ attribute: attrId, value: val });
      }
    }
    return result;
  }

  function initManageSectionsModal(modal) {
    var root = modal.querySelector('#mgmtRoot');
    var tree = modal.querySelector('#mgmtSectionTree');
    var addSectionBtn = modal.querySelector('#mgmtAddSectionBtn');
    var addAttributeBtn = modal.querySelector('#mgmtAddAttributeBtn');
    var attrList = modal.querySelector('#mgmtAttributesList');
    var saveBtn = modal.querySelector('#mgmtSaveBtn');
    if (!root || !tree || !attrList) return;

    var slug = root.getAttribute('data-project') || projectSlug;
    var deletedAttrKeys = [];

    function cloneTemplate(id) {
      var tpl = modal.querySelector('#' + id);
      return tpl && tpl.content ? tpl.content.firstElementChild.cloneNode(true) : null;
    }

    function newSectionItem(title) {
      var item = cloneTemplate('mgmtSectionTemplate');
      if (!item) return null;
      var input = item.querySelector('.section-name-input');
      if (input) input.value = title;
      return item;
    }

    function renumberMgmtSections() {
      var topItems = tree.querySelectorAll(':scope > .section-item');
      for (var i = 0; i < topItems.length; i++) {
        var num = (i + 1) + '';
        var numEl = topItems[i].querySelector(':scope > .section-item-content .section-number');
        if (numEl) numEl.textContent = num;
        var childContainer = topItems[i].querySelector(':scope > .section-children');
        if (childContainer) renumberMgmtChildren(childContainer, num);
      }
    }

    function renumberMgmtChildren(container, parentNum) {
      var items = container.querySelectorAll(':scope > .section-item');
      for (var j = 0; j < items.length; j++) {
        var subNum = parentNum + '.' + (j + 1);
        var numEl = items[j].querySelector(':scope > .section-item-content .section-number');
        if (numEl) numEl.textContent = subNum;
        var childContainer = items[j].querySelector(':scope > .section-children');
        if (childContainer) renumberMgmtChildren(childContainer, subNum);
      }
    }

    renumberMgmtSections();

    tree.addEventListener('click', function (e) {
      var target = e.target.closest('button');
      if (!target) return;
      var sectionItem = target.closest('.section-item');
      if (!sectionItem) return;
      var action = target.getAttribute('data-section-action');

      if (action === 'toggle-description') {
        var wrapper = sectionItem.querySelector(':scope > .section-desc-wrapper');
        if (wrapper) {
          var isVisible = wrapper.style.display !== 'none';
          wrapper.style.display = isVisible ? 'none' : '';
          target.classList.toggle('btn-outline-secondary', isVisible);
          target.classList.toggle('btn-secondary', !isVisible);
          if (!isVisible) {
            var ta = wrapper.querySelector('.section-desc-input');
            if (ta) ta.focus();
          }
        }
        return;
      }

      if (action === 'remove') {
        sectionItem.remove();
        renumberMgmtSections();
        return;
      }

      if (action === 'add-child') {
        var children = sectionItem.querySelector(':scope > .section-children');
        if (!children) {
          children = document.createElement('div');
          children.className = 'section-children';
          sectionItem.appendChild(children);
        }
        var sub = newSectionItem(gettext('New section'));
        if (!sub) return;
        children.appendChild(sub);
        renumberMgmtSections();
        sub.querySelector('.section-name-input').focus();
        sub.querySelector('.section-name-input').select();
        return;
      }

      if (action === 'up') {
        var prev = sectionItem.previousElementSibling;
        while (prev && !prev.classList.contains('section-item')) prev = prev.previousElementSibling;
        if (prev) {
          sectionItem.parentNode.insertBefore(sectionItem, prev);
          renumberMgmtSections();
        }
        return;
      }

      if (action === 'down') {
        var next = sectionItem.nextElementSibling;
        while (next && !next.classList.contains('section-item')) next = next.nextElementSibling;
        if (next) {
          if (next.nextSibling) {
            sectionItem.parentNode.insertBefore(sectionItem, next.nextSibling);
          } else {
            sectionItem.parentNode.appendChild(sectionItem);
          }
          renumberMgmtSections();
        }
        return;
      }

      if (action === 'indent') {
        var prevSibling = sectionItem.previousElementSibling;
        while (prevSibling && !prevSibling.classList.contains('section-item')) {
          prevSibling = prevSibling.previousElementSibling;
        }
        if (!prevSibling) return;
        var targetChildren = prevSibling.querySelector(':scope > .section-children');
        if (!targetChildren) {
          targetChildren = document.createElement('div');
          targetChildren.className = 'section-children';
          prevSibling.appendChild(targetChildren);
        }
        targetChildren.appendChild(sectionItem);
        renumberMgmtSections();
        return;
      }

      if (action === 'outdent') {
        var parentContainer = sectionItem.parentNode;
        if (!parentContainer || !parentContainer.classList.contains('section-children')) return;
        var parentSection = parentContainer.closest('.section-item');
        if (!parentSection) return;
        var grandparent = parentSection.parentNode;
        if (parentSection.nextSibling) {
          grandparent.insertBefore(sectionItem, parentSection.nextSibling);
        } else {
          grandparent.appendChild(sectionItem);
        }
        if (parentContainer.querySelectorAll(':scope > .section-item').length === 0) {
          parentContainer.remove();
        }
        renumberMgmtSections();
        return;
      }
    });

    var draggedSection = null;
    var dropBar = document.createElement('div');
    dropBar.className = 'section-drop-bar';
    var currentDropTarget = null;

    function getAllSectionItems() {
      return Array.prototype.slice.call(tree.querySelectorAll('.section-item'));
    }

    function clearDropHighlights() {
      var all = tree.querySelectorAll('.section-drop-child');
      for (var i = 0; i < all.length; i++) all[i].classList.remove('section-drop-child');
      if (dropBar.parentNode) dropBar.parentNode.removeChild(dropBar);
      currentDropTarget = null;
    }

    function isDescendantOf(item, ancestor) {
      var el = item.parentNode;
      while (el) {
        if (el === ancestor) return true;
        el = el.parentNode;
      }
      return false;
    }

    function showDropIndicator(targetItem, zone) {
      if (!targetItem) { clearDropHighlights(); return; }
      var all = tree.querySelectorAll('.section-drop-child');
      for (var i = 0; i < all.length; i++) all[i].classList.remove('section-drop-child');
      if (dropBar.parentNode) dropBar.parentNode.removeChild(dropBar);

      if (zone === 'child') {
        var content = targetItem.querySelector(':scope > .section-item-content');
        if (content) content.classList.add('section-drop-child');
        currentDropTarget = { el: targetItem, zone: 'child' };
        return;
      }

      if (zone === 'before') {
        targetItem.parentNode.insertBefore(dropBar, targetItem);
      } else {
        if (targetItem.nextSibling) {
          targetItem.parentNode.insertBefore(dropBar, targetItem.nextSibling);
        } else {
          targetItem.parentNode.appendChild(dropBar);
        }
      }
      currentDropTarget = { el: targetItem, zone: zone };
    }

    function findDropTarget(ev) {
      var items = getAllSectionItems();
      var closest = null;
      var closestDist = Infinity;
      var closestZone = 'after';

      for (var i = 0; i < items.length; i++) {
        if (items[i] === draggedSection) continue;
        if (isDescendantOf(items[i], draggedSection)) continue;
        var content = items[i].querySelector(':scope > .section-item-content');
        if (!content) continue;
        var rect = content.getBoundingClientRect();
        var height = rect.height;
        var midY = rect.top + height / 2;
        var dist = Math.abs(ev.clientY - midY);

        if (dist < closestDist) {
          closestDist = dist;
          closest = items[i];
          var relY = ev.clientY - rect.top;
          if (relY < height * 0.3) {
            closestZone = 'before';
          } else if (relY > height * 0.7) {
            closestZone = 'after';
          } else {
            closestZone = 'child';
          }
        }
      }
      return closest ? { el: closest, zone: closestZone } : null;
    }

    function performDrop(target) {
      if (!target || !draggedSection) return;
      var el = target.el;
      var zone = target.zone;

      if (zone === 'before') {
        el.parentNode.insertBefore(draggedSection, el);
      } else if (zone === 'after') {
        if (el.nextSibling) {
          el.parentNode.insertBefore(draggedSection, el.nextSibling);
        } else {
          el.parentNode.appendChild(draggedSection);
        }
      } else if (zone === 'child') {
        var children = el.querySelector(':scope > .section-children');
        if (!children) {
          children = document.createElement('div');
          children.className = 'section-children';
          el.appendChild(children);
        }
        children.appendChild(draggedSection);
      }

      var allChildContainers = tree.querySelectorAll('.section-children');
      for (var c = 0; c < allChildContainers.length; c++) {
        if (allChildContainers[c].querySelectorAll(':scope > .section-item').length === 0) {
          allChildContainers[c].remove();
        }
      }
    }

    tree.addEventListener('mousedown', function (e) {
      var handle = e.target.closest('.section-drag-handle');
      if (!handle) return;
      var item = handle.closest('.section-item');
      if (!item) return;
      e.preventDefault();
      draggedSection = item;
      var rect = item.getBoundingClientRect();
      var offsetY = e.clientY - rect.top;

      item.classList.add('section-dragging');
      item.style.position = 'fixed';
      item.style.width = rect.width + 'px';
      item.style.left = rect.left + 'px';
      item.style.top = (e.clientY - offsetY) + 'px';
      item.style.zIndex = '9999';
      item.style.pointerEvents = 'none';

      var placeholder = document.createElement('div');
      placeholder.className = 'section-drag-spacer';
      placeholder.style.height = rect.height + 'px';
      item.parentNode.insertBefore(placeholder, item.nextSibling);

      function onMouseMove(ev) {
        item.style.top = (ev.clientY - offsetY) + 'px';
        var target = findDropTarget(ev);
        if (target) {
          showDropIndicator(target.el, target.zone);
        } else {
          clearDropHighlights();
        }
      }

      function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);

        if (placeholder.parentNode) placeholder.remove();

        if (currentDropTarget) {
          performDrop(currentDropTarget);
        }

        item.classList.remove('section-dragging');
        item.style.position = '';
        item.style.width = '';
        item.style.left = '';
        item.style.top = '';
        item.style.zIndex = '';
        item.style.pointerEvents = '';
        clearDropHighlights();
        draggedSection = null;
        renumberMgmtSections();
      }

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    });

    if (addSectionBtn) {
      addSectionBtn.addEventListener('click', function () {
        var item = newSectionItem(gettext('New section'));
        if (!item) return;
        tree.appendChild(item);
        renumberMgmtSections();
        item.querySelector('.section-name-input').focus();
        item.querySelector('.section-name-input').select();
      });
    }

    if (addAttributeBtn) {
      addAttributeBtn.addEventListener('click', function () {
        var row = cloneTemplate('mgmtAttributeTemplate');
        if (!row) return;
        attrList.appendChild(row);
        row.querySelector('.attr-name-input').focus();
      });
    }

    attrList.addEventListener('click', function (e) {
      var remove = e.target.closest('.attribute-row-custom [data-attribute-action="remove"]');
      if (!remove) return;
      var row = remove.closest('.attribute-row-custom');
      var attrKey = row.getAttribute('data-attr-key');
      if (!attrKey) {
        row.remove();
        return;
      }
      var attrNameInput = row.querySelector('.attr-name-input');
      window.showConfirmModal({
        title: gettext('Remove Attribute'),
        bodyText: interpolate(gettext('Remove attribute "%(name)s"? Its values on every item are deleted when you save.'), { name: attrNameInput ? attrNameInput.value : '' }, true),
        confirmText: gettext('Remove'),
        onConfirm: function () {
          deletedAttrKeys.push(attrKey);
          row.remove();
        }
      });
    });

    attrList.addEventListener('change', function (e) {
      if (!e.target.classList.contains('attr-type-select')) return;
      var row = e.target.closest('.attribute-row-custom');
      var wrapper = row ? row.querySelector('.attr-options-wrapper') : null;
      if (!wrapper) return;
      wrapper.style.display = (e.target.value === 'dropdown' || e.target.value === 'multiselect') ? '' : 'none';
    });

    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + gettext('Saving...');

        saveSections().then(saveAttributes).then(function () {
          if (window.showToast) window.showToast(gettext('Project structure saved.'), 'success');
          window.location.reload();
        }).catch(function (err) {
          if (window.showToast) window.showToast(interpolate(gettext('Not saved: %(error)s'), { error: err.message }, true), 'danger');
          window.Modal.refresh();
        });
      });
    }

    function checkedJson(response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (response.ok && data.ok !== false) return data;
        var message = data.error || data.detail;
        if (!message) {
          var fields = data.errors || data;
          var first = Object.keys(fields)[0];
          message = first ? [].concat(fields[first])[0] : gettext('The server refused the change.');
        }
        throw new Error(message);
      });
    }

    function saveSections() {
      var sections = [];
      function collectLevel(container, parentRef) {
        var items = container.querySelectorAll(':scope > .section-item');
        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          var numberEl = item.querySelector(':scope > .section-item-content .section-number');
          var titleEl = item.querySelector(':scope > .section-item-content .section-name-input');
          var descEl = item.querySelector(':scope > .section-desc-wrapper .section-desc-input');
          var sectionId = item.getAttribute('data-section-id') || '';

          sections.push({
            id: sectionId ? parseInt(sectionId) : null,
            key: item.getAttribute('data-section-key') || '',
            title: titleEl ? titleEl.value.trim() : '',
            description: descEl ? descEl.value.trim() : '',
            number: numberEl ? numberEl.textContent.trim() : '',
            parent_ref: parentRef,
            ref: 'ref-' + sections.length,
            order: sections.length,
          });

          var childContainer = item.querySelector(':scope > .section-children');
          if (childContainer) {
            collectLevel(childContainer, 'ref-' + (sections.length - 1));
          }
        }
      }
      collectLevel(tree, '');

      return fetchAllPages('sections/').then(function (currentSections) {
        var keepIds = new Set();
        sections.forEach(function (s) { if (s.id) keepIds.add(s.id); });

        var toDelete = [];
        currentSections.forEach(function (s) {
          if (!keepIds.has(s.id)) toDelete.push(s.public_key);
        });

        var deleteChain = Promise.resolve();
        toDelete.reverse().forEach(function (sid) {
          deleteChain = deleteChain.then(function () {
            return fetch('/projects/' + slug + '/sections/' + sid + '/delete/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
              credentials: 'same-origin',
              body: '{}',
            }).then(checkedJson);
          });
        });

        return deleteChain.then(function () {
          var refToId = {};
          var chain = Promise.resolve();

          sections.forEach(function (s) {
            chain = chain.then(function () {
              var parentId = null;
              if (s.parent_ref && refToId[s.parent_ref] !== undefined) {
                parentId = refToId[s.parent_ref];
              }

              if (s.id) {
                refToId[s.ref] = s.id;
                return fetch('/projects/' + slug + '/sections/' + s.key + '/update/', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
                  credentials: 'same-origin',
                  body: JSON.stringify({ title: s.title, description: s.description, parent_id: parentId }),
                }).then(checkedJson);
              }
              return fetch('/projects/' + slug + '/sections/create/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
                credentials: 'same-origin',
                body: JSON.stringify({ title: s.title || gettext('New section'), description: s.description, parent_id: parentId }),
              }).then(checkedJson).then(function (data) {
                refToId[s.ref] = data.section.id;
              });
            });
          });

          return chain.then(function () {
            var orderList = [];
            sections.forEach(function (s, idx) {
              var sectionId = s.id || refToId[s.ref];
              if (sectionId) {
                var parentId = null;
                if (s.parent_ref && refToId[s.parent_ref] !== undefined) {
                  parentId = refToId[s.parent_ref];
                }
                orderList.push({ id: sectionId, order: idx, parent_id: parentId });
              }
            });

            return fetch('/projects/' + slug + '/sections/reorder/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
              credentials: 'same-origin',
              body: JSON.stringify({ order: orderList }),
            }).then(checkedJson);
          });
        });
      });
    }

    function saveAttributes() {
      var deleteChain = Promise.resolve();
      deletedAttrKeys.forEach(function (attrKey) {
        deleteChain = deleteChain.then(function () {
          return fetchApi(apiUrl('attributes/' + attrKey + '/'), { method: 'DELETE' }).then(checkedJson);
        });
      });

      return deleteChain.then(function () {
        var rows = attrList.querySelectorAll('.attribute-row-custom');
        var chain = Promise.resolve();

        rows.forEach(function (row) {
          chain = chain.then(function () {
            var nameInput = row.querySelector('.attr-name-input');
            var typeSelect = row.querySelector('.attr-type-select');
            var optionsInput = row.querySelector('.attr-options-input');
            var attrKey = row.getAttribute('data-attr-key');

            var name = nameInput ? nameInput.value.trim() : '';
            var fieldType = typeSelect ? typeSelect.value : 'text';
            var optionsStr = optionsInput ? optionsInput.value.trim() : '';
            var options = [];
            if (fieldType === 'dropdown' || fieldType === 'multiselect') {
              options = optionsStr.split(',').map(function (o) { return o.trim(); }).filter(Boolean);
            }

            if (!name) return Promise.resolve();

            if (attrKey) {
              return fetchApi(apiUrl('attributes/' + attrKey + '/'), {
                method: 'PATCH',
                body: JSON.stringify({ name: name, field_type: fieldType, options: options }),
              }).then(checkedJson);
            }
            return fetchApi(apiUrl('attributes/'), {
              method: 'POST',
              body: JSON.stringify({ name: name, field_type: fieldType, options: options }),
            }).then(checkedJson);
          });
        });

        return chain;
      });
    }
  }

  window.ProjectEditor = {
    apiUrl: apiUrl,
    fetchApi: fetchApi,
    selectedItemPk: function () { return selectedItemPk; },
    selectedItemKey: function () { return selectedItemKey; },
    loadItemDetail: loadItemDetail,
    escapeHtml: escapeHtml,
    stripHtml: stripHtml,
    formatDate: formatDate,
    statusBadge: statusBadge,
    priorityBadge: priorityBadge,
  };

})();
