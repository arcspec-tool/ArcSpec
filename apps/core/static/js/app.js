(function () {
  'use strict';

  var sidebar = document.getElementById('sidebar');
  var sidebarToggle = document.getElementById('sidebarToggle');
  var sidebarBackdrop = document.getElementById('sidebarBackdrop');

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('show');
  }

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.remove('show');
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', openSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

  var TOAST_TYPES = { success: 'success', danger: 'danger', error: 'danger', warning: 'warning', info: 'info' };
  var TOAST_TIMEOUTS = { success: 3000, danger: 4000, warning: 4000, info: 3000 };
  var toasts = {};
  var toastCounter = 0;

  function toastType(type) {
    return TOAST_TYPES[type] || 'info';
  }

  function removeToast(id, reason) {
    var entry = toasts[id];
    if (!entry) return;
    clearTimeout(entry.timer);
    delete toasts[id];
    entry.element.classList.remove('show');
    setTimeout(function () { entry.element.remove(); }, 300);
    document.dispatchEvent(new CustomEvent(reason === 'expired' ? 'toast:expired' : 'toast:dismissed', { detail: { id: id, type: entry.type } }));
  }

  function showToast(opts) {
    if (typeof opts === 'string') opts = { message: opts, type: arguments[1] };
    opts = opts || {};
    var container = document.getElementById('toastContainer');
    if (!container) return null;
    var type = toastType(opts.type);
    var id = opts.id || ('toast-' + (++toastCounter));
    if (toasts[id]) removeToast(id, 'replaced');

    var toast = document.createElement('div');
    toast.className = 'toast align-items-center text-bg-' + type + ' border-0 show';
    toast.setAttribute('role', 'alert');
    toast.setAttribute('data-toast-id', id);

    var flex = document.createElement('div');
    flex.className = 'd-flex';
    var body = document.createElement('div');
    body.className = 'toast-body';
    if (opts.title) {
      var title = document.createElement('div');
      title.className = 'fw-semibold';
      title.textContent = opts.title;
      body.appendChild(title);
    }
    body.appendChild(document.createTextNode(opts.message || ''));
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
    closeBtn.setAttribute('aria-label', gettext('Close'));
    closeBtn.setAttribute('data-toast-dismiss', id);
    flex.appendChild(body);
    flex.appendChild(closeBtn);
    toast.appendChild(flex);
    container.appendChild(toast);

    var timeout = typeof opts.timeout === 'number' ? opts.timeout : TOAST_TIMEOUTS[type];
    toasts[id] = { element: toast, type: type, timer: setTimeout(function () { removeToast(id, 'expired'); }, timeout) };
    return id;
  }

  window.Toast = {
    show: showToast,
    dismiss: function (id) { removeToast(id, 'dismissed'); }
  };
  window.showToast = function (message, type, opts) {
    return showToast(Object.assign({ message: message, type: type || 'success' }, opts || {}));
  };

  document.addEventListener('toast:show', function (e) { showToast(e.detail || {}); });
  document.addEventListener('toast:dismiss', function (e) { if (e.detail && e.detail.id) removeToast(e.detail.id, 'dismissed'); });
  document.addEventListener('click', function (e) {
    var dismiss = e.target.closest('[data-toast-dismiss]');
    if (dismiss) removeToast(dismiss.getAttribute('data-toast-dismiss'), 'dismissed');
  });

  var pageMessages = document.getElementById('page-messages');
  if (pageMessages) {
    var messages;
    try { messages = JSON.parse(pageMessages.textContent); } catch (err) { messages = []; }
    messages.forEach(function (entry) {
      showToast({ message: entry.message, type: entry.type });
    });
  }

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      var searchInput = document.getElementById('globalSearchInput');
      if (searchInput) searchInput.focus();
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      closeSidebar();
      var results = document.getElementById('globalSearchResults');
      if (results) results.style.display = 'none';
    }
  });

  var globalSearchInput = document.getElementById('globalSearchInput');
  var globalSearchResults = document.getElementById('globalSearchResults');
  var searchTimer = null;

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function stripHtml(html) {
    if (!html) return '';
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    return tmp.textContent || '';
  }

  function performGlobalSearch(query) {
    if (query.length < 2) {
      if (globalSearchResults) globalSearchResults.style.display = 'none';
      return;
    }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/projects/search/?q=' + encodeURIComponent(query));
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.onload = function () {
      if (xhr.status !== 200 || !globalSearchResults) return;
      var data = JSON.parse(xhr.responseText);
      var html = '';

      if (data.projects.length > 0) {
        html += '<div class="menu-heading">' + gettext('Projects') + '</div>';
        data.projects.forEach(function (p) {
          html += '<a class="menu-item" href="/projects/' + escapeHtml(p.slug) + '/">' +
            '<i class="bi bi-folder2-open menu-item-icon" aria-hidden="true"></i><span class="menu-item-text">' + escapeHtml(p.name) +
            ' <span class="badge bg-secondary bg-opacity-10 text-secondary ms-1">' + escapeHtml(p.status) + '</span></span></a>';
        });
      }

      if (data.items.length > 0) {
        html += '<div class="menu-heading">' + gettext('Items') + '</div>';
        data.items.forEach(function (i) {
          html += '<a class="menu-item" href="/projects/' + escapeHtml(i.project_slug) + '/#' + escapeHtml(encodeURIComponent(i.item_id)) + '">' +
            '<i class="bi bi-file-text menu-item-icon" aria-hidden="true"></i><span class="menu-item-text">' +
            '<strong>' + escapeHtml(i.item_id) + '</strong> ' + escapeHtml(stripHtml(i.text)) +
            ' <span class="text-muted small">(' + escapeHtml(i.project_name) + ')</span></span></a>';
        });
      }

      if (data.projects.length === 0 && data.items.length === 0) {
        html = '<div class="menu-note text-center">' + gettext('No results found') + '</div>';
      }

      globalSearchResults.innerHTML = html;
      globalSearchResults.style.display = 'block';
    };
    xhr.send();
  }

  if (globalSearchInput) {
    globalSearchInput.addEventListener('input', function () {
      clearTimeout(searchTimer);
      var query = globalSearchInput.value.trim();
      searchTimer = setTimeout(function () {
        performGlobalSearch(query);
      }, 300);
    });

    globalSearchInput.addEventListener('focus', function () {
      if (globalSearchInput.value.trim().length >= 2 && globalSearchResults && globalSearchResults.innerHTML) {
        globalSearchResults.style.display = 'block';
      }
    });
  }

  document.addEventListener('click', function (e) {
    if (globalSearchResults && !e.target.closest('.topbar-search')) {
      globalSearchResults.style.display = 'none';
    }
  });

  function lockPanelHeights(grid) {
    if (!grid || grid.hasAttribute('data-locked')) return;
    if (getComputedStyle(grid).gridTemplateColumns.split(' ').length < 2) return;
    grid.querySelectorAll('.dash-panel').forEach(function (panel) {
      panel.style.height = panel.offsetHeight + 'px';
    });
    grid.setAttribute('data-locked', '');
  }

  window.loadMoreFeed = function (btn, list, params, doneText, onPage) {
    lockPanelHeights(btn.closest('.dash-panels, .profile-panels'));
    btn.disabled = true;
    btn.textContent = gettext('Loading...');
    fetch(btn.getAttribute('data-url') + '?' + new URLSearchParams(params).toString(), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (response) {
      var redirectTo = response.status === 204 && response.headers.get('X-Redirect-To');
      if (redirectTo) {
        window.location.href = redirectTo;
        return null;
      }
      if (!response.ok) throw new Error(response.status);
      return response.json();
    }).then(function (data) {
      if (!data) return;
      var holder = document.createElement('template');
      holder.innerHTML = data.html;
      var added = onPage(data, Array.prototype.slice.call(holder.content.children));
      if (added.length) list.scrollTop = Math.max(0, added[0].offsetTop - 24);
      if (data.has_more) {
        btn.disabled = false;
        btn.textContent = gettext('Load more');
      } else {
        btn.textContent = doneText;
      }
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = gettext('Load more');
      window.showToast(gettext('Could not load more. Try again.'), 'danger');
    });
  };

  var loadMoreActivity = document.getElementById('loadMoreActivity');
  if (loadMoreActivity) {
    loadMoreActivity.addEventListener('click', function () {
      var btn = this;
      var list = document.getElementById(btn.getAttribute('data-list'));
      window.loadMoreFeed(btn, list, {
        offset: btn.getAttribute('data-offset'),
        until: btn.getAttribute('data-until')
      }, gettext('No more activity'), function (data, rows) {
        rows.forEach(function (row) { list.appendChild(row); });
        btn.setAttribute('data-offset', parseInt(btn.getAttribute('data-offset'), 10) + rows.length);
        return rows;
      });
    });
  }

  var MENU_PAD = 8;
  var MENU_GAP = 4;
  var SUBMENU_OPEN_DELAY = 150;
  var SUBMENU_CLOSE_DELAY = 300;
  var MENU_ITEM_SELECTOR = '[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"]';
  var PANEL_FOCUS_SELECTOR = 'select, input:not([type="hidden"]), textarea, button, [href], [tabindex]:not([tabindex="-1"])';
  var menuState = null;
  var menuTimers = { open: null, close: null };
  var suppressTriggerClick = null;

  function menuItems(menu) {
    return Array.prototype.filter.call(menu.querySelectorAll(MENU_ITEM_SELECTOR), function (item) {
      return item.closest('.menu') === menu && !item.hidden;
    });
  }

  function focusMenuItem(item) {
    if (item) item.focus({ preventScroll: true });
  }

  function isMenuOpen(menu) {
    return menu.matches(':popover-open');
  }

  function showMenuElement(menu) {
    if (!isMenuOpen(menu)) menu.showPopover();
  }

  function hideMenuElement(menu) {
    if (isMenuOpen(menu)) menu.hidePopover();
  }

  function parentItemOf(submenu) {
    var previous = submenu.previousElementSibling;
    if (previous && previous.getAttribute('aria-controls') === submenu.id) return previous;
    return document.querySelector('[aria-controls="' + submenu.id + '"]');
  }

  function menuDetail(extra) {
    var base = menuState ? { id: menuState.root.id, menu: menuState.root, trigger: menuState.trigger, target: menuState.target, via: menuState.via } : {};
    return Object.assign(base, extra || {});
  }

  function placeMenu(el, anchor, placement, align) {
    var vw = document.documentElement.clientWidth;
    var vh = document.documentElement.clientHeight;
    el.style.maxHeight = '';
    var w = el.offsetWidth;
    var h = el.offsetHeight;
    var maxH = vh - 2 * MENU_PAD;
    if (h > maxH) {
      el.style.maxHeight = maxH + 'px';
      h = maxH;
    }
    var x, y;
    var originX = 'left';
    var originY = 'top';
    if (placement === 'point') {
      x = anchor.x;
      y = anchor.y;
      if (x + w > vw - MENU_PAD) { x = anchor.x - w; originX = 'right'; }
      if (y + h > vh - MENU_PAD) { y = anchor.y - h; originY = 'bottom'; }
    } else if (placement === 'right') {
      x = anchor.menu.right - MENU_GAP;
      if (x + w > vw - MENU_PAD) { x = anchor.menu.left - w + MENU_GAP; originX = 'right'; }
      y = anchor.item.top - 6;
      if (y + h > vh - MENU_PAD) y = vh - MENU_PAD - h;
    } else {
      if (align === 'end') {
        x = anchor.right - w;
        originX = 'right';
        if (x < MENU_PAD) { x = anchor.left; originX = 'left'; }
      } else {
        x = anchor.left;
        if (x + w > vw - MENU_PAD) { x = anchor.right - w; originX = 'right'; }
      }
      y = anchor.bottom + MENU_GAP;
      if (y + h > vh - MENU_PAD) {
        if (anchor.top - MENU_GAP - h >= MENU_PAD) {
          y = anchor.top - MENU_GAP - h;
          originY = 'bottom';
        } else {
          y = Math.max(MENU_PAD, vh - MENU_PAD - h);
        }
      }
    }
    x = Math.min(Math.max(x, MENU_PAD), Math.max(MENU_PAD, vw - MENU_PAD - w));
    y = Math.min(Math.max(y, MENU_PAD), Math.max(MENU_PAD, vh - MENU_PAD - h));
    el.style.left = Math.round(x) + 'px';
    el.style.top = Math.round(y) + 'px';
    el.style.transformOrigin = originX + ' ' + originY;
  }

  function repositionMenus() {
    if (!menuState) return;
    var root = menuState.root;
    var anchor = menuState.anchor;
    var rect = anchor && anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : anchor;
    var align = (menuState.trigger && menuState.trigger.getAttribute('data-menu-align')) || root.getAttribute('data-menu-align');
    placeMenu(root, rect, menuState.placement, align);
    for (var i = 1; i < menuState.open.length; i++) {
      var item = parentItemOf(menuState.open[i]);
      if (item) placeMenu(menuState.open[i], { menu: menuState.open[i - 1].getBoundingClientRect(), item: item.getBoundingClientRect() }, 'right');
    }
  }

  function closeSubmenusFrom(parentMenu) {
    if (!menuState) return;
    var index = menuState.open.indexOf(parentMenu);
    if (index === -1) return;
    while (menuState.open.length > index + 1) {
      var sub = menuState.open.pop();
      hideMenuElement(sub);
      var item = parentItemOf(sub);
      if (item) item.setAttribute('aria-expanded', 'false');
    }
  }

  function openSubmenu(item, focusFirst) {
    var sub = document.getElementById(item.getAttribute('aria-controls'));
    var parentMenu = item.closest('.menu');
    if (!sub || !menuState || menuState.open.indexOf(parentMenu) === -1) return;
    closeSubmenusFrom(parentMenu);
    item.setAttribute('aria-expanded', 'true');
    sub.dispatchEvent(new CustomEvent('menu:open', { bubbles: true, detail: menuDetail({ submenu: sub, parentItem: item }) }));
    showMenuElement(sub);
    placeMenu(sub, { menu: parentMenu.getBoundingClientRect(), item: item.getBoundingClientRect() }, 'right');
    menuState.open.push(sub);
    if (focusFirst) focusMenuItem(menuItems(sub)[0]);
  }

  function closeSubmenu(sub, focusParent) {
    var item = parentItemOf(sub);
    var parentMenu = item ? item.closest('.menu') : null;
    if (parentMenu) closeSubmenusFrom(parentMenu);
    if (focusParent) focusMenuItem(item);
  }

  function closeMenus(reason) {
    if (!menuState) return;
    var state = menuState;
    menuState = null;
    clearTimeout(menuTimers.open);
    clearTimeout(menuTimers.close);
    var active = document.activeElement;
    var focusInside = active && state.root.contains(active);
    for (var i = state.open.length - 1; i >= 0; i--) {
      hideMenuElement(state.open[i]);
      var item = i > 0 ? parentItemOf(state.open[i]) : null;
      if (item) item.setAttribute('aria-expanded', 'false');
    }
    if (state.trigger) state.trigger.setAttribute('aria-expanded', 'false');
    state.root.removeAttribute('data-menu-via');
    if (reason !== 'focusout' && state.restore && document.contains(state.restore) && (focusInside || document.activeElement === document.body)) {
      state.restore.focus({ preventScroll: true });
    }
    state.root.dispatchEvent(new CustomEvent('menu:close', { bubbles: true, detail: { id: state.root.id, menu: state.root, trigger: state.trigger, target: state.target, reason: reason } }));
  }

  function openMenu(menu, opts) {
    if (typeof menu === 'string') menu = document.getElementById(menu);
    if (!menu) return null;
    opts = opts || {};
    if (menuState) closeMenus(menuState.root === menu ? 'reopened' : 'replaced');
    var trigger = opts.trigger || null;
    var targetSelector = menu.getAttribute('data-menu-target');
    var target = opts.target || (trigger && targetSelector ? trigger.closest(targetSelector) : null) || trigger;
    menuState = {
      root: menu,
      trigger: trigger,
      target: target,
      via: opts.via || 'pointer',
      open: [menu],
      restore: opts.restore || trigger || null,
      anchor: opts.anchor || trigger,
      placement: opts.placement || 'bottom',
      openedAt: performance.now()
    };
    var proceed = menu.dispatchEvent(new CustomEvent('menu:open', { bubbles: true, cancelable: true, detail: menuDetail() }));
    if (!proceed) {
      menuState = null;
      return null;
    }
    showMenuElement(menu);
    repositionMenus();
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    menu.setAttribute('data-menu-via', menuState.via);
    if (menu.getAttribute('role') !== 'menu') {
      var control = menu.querySelector(PANEL_FOCUS_SELECTOR);
      (control || menu).focus({ preventScroll: true });
      return menu;
    }
    var items = menuItems(menu);
    var focusMode = opts.focus || (menuState.via === 'keyboard' ? 'first' : 'none');
    if (focusMode === 'none' || !items.length) menu.focus({ preventScroll: true });
    else if (focusMode === 'last') focusMenuItem(items[items.length - 1]);
    else focusMenuItem(items[0]);
    return menu;
  }

  function activateMenuItem(item, event) {
    if (item.getAttribute('aria-disabled') === 'true') {
      event.preventDefault();
      return;
    }
    if (item.getAttribute('aria-haspopup')) {
      event.preventDefault();
      var sub = document.getElementById(item.getAttribute('aria-controls'));
      if (sub && item.getAttribute('aria-expanded') === 'true') closeSubmenu(sub, true);
      else openSubmenu(item, true);
      return;
    }
    var menu = item.closest('.menu');
    var role = item.getAttribute('role');
    var checked = null;
    if (role === 'menuitemcheckbox') {
      checked = item.getAttribute('aria-checked') !== 'true';
      item.setAttribute('aria-checked', checked ? 'true' : 'false');
    } else if (role === 'menuitemradio') {
      var group = item.closest('[role="group"]') || menu;
      Array.prototype.forEach.call(group.querySelectorAll('[role="menuitemradio"]'), function (radio) {
        radio.setAttribute('aria-checked', radio === item ? 'true' : 'false');
      });
      checked = true;
    }
    var state = menuState;
    var detail = menuDetail({
      item: item,
      action: item.getAttribute('data-action'),
      value: item.getAttribute('data-value'),
      checked: checked,
      submenu: state && menu !== state.root ? menu : null
    });
    var keepOpen = role === 'menuitemcheckbox' || menu.hasAttribute('data-menu-keep-open') || (state && state.root.hasAttribute('data-menu-keep-open'));
    if (!keepOpen) closeMenus('select');
    item.dispatchEvent(new CustomEvent('menu:select', { bubbles: true, detail: detail }));
  }

  function typeAhead(items, index, key) {
    var lower = key.toLowerCase();
    for (var offset = 1; offset <= items.length; offset++) {
      var candidate = items[(index + offset) % items.length];
      if (candidate.textContent.trim().toLowerCase().indexOf(lower) === 0) return candidate;
    }
    return null;
  }

  function onMenuKeydown(e) {
    if (!menuState) return;
    var menu = e.target.closest ? e.target.closest('.menu') : null;
    if (!menu || menuState.open.indexOf(menu) === -1) return;
    if (menu.getAttribute('role') !== 'menu') {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMenus('escape');
      }
      return;
    }
    var items = menuItems(menu);
    var index = items.indexOf(document.activeElement);
    var handled = true;
    switch (e.key) {
      case 'ArrowDown':
        focusMenuItem(items[index === -1 || index === items.length - 1 ? 0 : index + 1]);
        break;
      case 'ArrowUp':
        focusMenuItem(items[index <= 0 ? items.length - 1 : index - 1]);
        break;
      case 'Home':
        focusMenuItem(items[0]);
        break;
      case 'End':
        focusMenuItem(items[items.length - 1]);
        break;
      case 'ArrowRight':
        if (index >= 0 && items[index].getAttribute('aria-haspopup')) openSubmenu(items[index], true);
        break;
      case 'ArrowLeft':
        if (menu !== menuState.root) closeSubmenu(menu, true);
        break;
      case 'Escape':
        if (menu !== menuState.root) closeSubmenu(menu, true);
        else closeMenus('escape');
        break;
      case 'Enter':
      case ' ':
        if (index >= 0) items[index].click();
        break;
      case 'Tab':
        closeMenus('tab');
        handled = false;
        break;
      default:
        handled = false;
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          var next = typeAhead(items, index, e.key);
          if (next) {
            focusMenuItem(next);
            handled = true;
          }
        }
    }
    if (handled) e.preventDefault();
  }

  function initMenus(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.menu[popover]'), function (menu) {
      if (!menu.hasAttribute('tabindex')) menu.setAttribute('tabindex', '-1');
    });
    Array.prototype.forEach.call((root || document).querySelectorAll('[data-menu-open]'), function (trigger) {
      var id = trigger.getAttribute('data-menu-open');
      var menu = document.getElementById(id);
      trigger.setAttribute('aria-haspopup', menu && menu.getAttribute('role') === 'dialog' ? 'dialog' : 'menu');
      if (!trigger.hasAttribute('aria-expanded')) trigger.setAttribute('aria-expanded', 'false');
      trigger.setAttribute('aria-controls', id);
    });
  }

  window.Menu = {
    open: openMenu,
    close: closeMenus,
    reposition: repositionMenus,
    init: initMenus,
    current: function () { return menuState ? { id: menuState.root.id, menu: menuState.root, trigger: menuState.trigger, target: menuState.target } : null; }
  };

  initMenus(document);
  document.addEventListener('modal:show', function (e) { initMenus(e.target); });

  document.addEventListener('pointerdown', function (e) {
    suppressTriggerClick = null;
    if (!menuState) return;
    var inside = e.target.closest ? e.target.closest('.menu') : null;
    if (inside && menuState.open.indexOf(inside) !== -1) return;
    var trigger = e.target.closest ? e.target.closest('[data-menu-open]') : null;
    if (trigger && trigger === menuState.trigger) suppressTriggerClick = trigger;
    closeMenus('dismiss');
  }, true);

  document.addEventListener('click', function (e) {
    var item = e.target.closest ? e.target.closest(MENU_ITEM_SELECTOR) : null;
    if (item && item.closest('.menu') && menuState && menuState.open.indexOf(item.closest('.menu')) !== -1) {
      activateMenuItem(item, e);
      return;
    }
    var closer = e.target.closest ? e.target.closest('[data-menu-close]') : null;
    if (closer && menuState && closer.closest('.menu') === menuState.root) closeMenus('select');
  }, true);

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest ? e.target.closest('[data-menu-open]') : null;
    var suppressed = suppressTriggerClick;
    suppressTriggerClick = null;
    if (!trigger) return;
    e.preventDefault();
    if (suppressed === trigger) return;
    var menu = document.getElementById(trigger.getAttribute('data-menu-open'));
    if (!menu) return;
    if (menuState && menuState.root === menu && menuState.trigger === trigger) {
      closeMenus('toggle');
      return;
    }
    openMenu(menu, { trigger: trigger, anchor: trigger, placement: 'bottom', via: e.detail === 0 ? 'keyboard' : 'pointer' });
  });

  document.addEventListener('keydown', function (e) {
    var trigger = e.target.closest ? e.target.closest('[data-menu-open]') : null;
    if (trigger && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      var menu = document.getElementById(trigger.getAttribute('data-menu-open'));
      if (menu) openMenu(menu, { trigger: trigger, anchor: trigger, placement: 'bottom', via: 'keyboard', focus: e.key === 'ArrowUp' ? 'last' : 'first' });
      return;
    }
    onMenuKeydown(e);
  });

  document.addEventListener('contextmenu', function (e) {
    var holder = e.target.closest ? e.target.closest('[data-menu-context]') : null;
    if (!holder) {
      if (menuState && !(e.target.closest && e.target.closest('.menu'))) closeMenus('dismiss');
      return;
    }
    var selector = holder.getAttribute('data-menu-context-target');
    var target = selector ? e.target.closest(selector) : holder;
    var menu = document.getElementById(holder.getAttribute('data-menu-context'));
    if (!target || !holder.contains(target) || !menu) return;
    e.preventDefault();
    var byPointer = !!(e.clientX || e.clientY);
    var rowTrigger = target.querySelector('[data-menu-open="' + menu.id + '"]');
    openMenu(menu, {
      trigger: rowTrigger,
      target: target,
      anchor: byPointer ? { x: e.clientX, y: e.clientY } : target,
      placement: byPointer ? 'point' : 'bottom',
      via: e.button === 2 ? 'pointer' : 'keyboard',
      focus: e.button === 2 ? 'none' : 'first',
      restore: rowTrigger || (document.activeElement !== document.body ? document.activeElement : null)
    });
  });

  document.addEventListener('pointermove', function (e) {
    if (!menuState) return;
    var item = e.target.closest ? e.target.closest(MENU_ITEM_SELECTOR) : null;
    if (!item || item.getAttribute('aria-disabled') === 'true') return;
    var menu = item.closest('.menu');
    if (menuState.open.indexOf(menu) === -1 || document.activeElement === item) return;
    item.focus({ preventScroll: true });
  });

  document.addEventListener('pointerover', function (e) {
    if (!menuState) return;
    var menu = e.target.closest ? e.target.closest('.menu') : null;
    if (!menu || menuState.open.indexOf(menu) === -1) return;
    clearTimeout(menuTimers.open);
    clearTimeout(menuTimers.close);
    var item = e.target.closest(MENU_ITEM_SELECTOR);
    var openChild = menuState.open[menuState.open.indexOf(menu) + 1] || null;
    if (item && item.getAttribute('aria-haspopup')) {
      if (document.getElementById(item.getAttribute('aria-controls')) === openChild) return;
      menuTimers.open = setTimeout(function () { if (menuState) openSubmenu(item, false); }, SUBMENU_OPEN_DELAY);
    } else if (openChild) {
      menuTimers.close = setTimeout(function () { if (menuState) closeSubmenusFrom(menu); }, SUBMENU_CLOSE_DELAY);
    }
  });

  document.addEventListener('focusin', function (e) {
    if (!menuState) return;
    var inside = e.target.closest ? e.target.closest('.menu') : null;
    if (inside && menuState.open.indexOf(inside) !== -1) return;
    if (e.target === menuState.trigger) return;
    closeMenus('focusout');
  });

  function anchorClipped(anchor) {
    if (!anchor || !anchor.getBoundingClientRect) return false;
    var rect = anchor.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var el = anchor.parentElement;
    while (el && el !== document.body) {
      var style = getComputedStyle(el);
      if (/auto|scroll|hidden/.test(style.overflowX + style.overflowY)) {
        var box = el.getBoundingClientRect();
        if (cx < box.left || cx > box.right || cy < box.top || cy > box.bottom) return true;
      }
      el = el.parentElement;
    }
    return cx < 0 || cy < 0 || cx > document.documentElement.clientWidth || cy > document.documentElement.clientHeight;
  }

  document.addEventListener('scroll', function (e) {
    if (!menuState) return;
    var el = e.target && e.target.nodeType === 1 ? e.target : null;
    if (el && el.closest('.menu') && menuState.open.indexOf(el.closest('.menu')) !== -1) return;
    if (menuState.placement === 'point') {
      if (performance.now() - menuState.openedAt > 100) closeMenus('scroll');
      return;
    }
    if (anchorClipped(menuState.anchor)) closeMenus('scroll');
    else repositionMenus();
  }, true);

  window.addEventListener('resize', function () { closeMenus('resize'); });

  var MODAL_TARGETS = { page: 'modalTarget', confirm: 'confirmTarget' };
  var modalState = { page: null, confirm: null };

  function modalUrl(name, params) {
    var query = [];
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === '') return;
      query.push(encodeURIComponent(key) + '=' + encodeURIComponent(String(value)));
    });
    return '/modals/' + encodeURIComponent(name) + '/' + (query.length ? '?' + query.join('&') : '');
  }

  function redirectTarget(response) {
    if (response.status === 204 && response.headers.get('X-Redirect-To')) return response.headers.get('X-Redirect-To');
    if (response.redirected) return response.url;
    return null;
  }

  function fetchModal(name, params) {
    return fetch(modalUrl(name, params), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    }).then(function (response) {
      var target = redirectTarget(response);
      if (target) {
        window.location.href = target;
        return null;
      }
      if (!response.ok) {
        window.showToast(gettext('The dialog could not be loaded.'), 'danger');
        return null;
      }
      return response.text();
    }).catch(function () {
      window.showToast(gettext('The dialog could not be loaded.'), 'danger');
      return null;
    });
  }

  function modalDetail(state, layer) {
    return { name: state.name, params: state.params, layer: layer, reason: state.reason };
  }

  function raiseConfirmLayer(el) {
    el.style.zIndex = '1080';
    el.addEventListener('shown.bs.modal', function () {
      var backdrops = document.querySelectorAll('.modal-backdrop');
      if (backdrops.length) backdrops[backdrops.length - 1].style.zIndex = '1075';
    }, { once: true });
  }

  function openModal(name, params, opts) {
    opts = opts || {};
    var layer = opts.layer === 'confirm' ? 'confirm' : 'page';
    var target = document.getElementById(MODAL_TARGETS[layer]);
    if (!target) return Promise.resolve(null);
    var existing = modalState[layer];
    if (existing && existing.loading) return Promise.resolve(null);
    if (existing && existing.instance) {
      return new Promise(function (resolve) {
        document.addEventListener('modal:hidden', function () {
          resolve(openModal(name, params, opts));
        }, { once: true });
        existing.instance.hide();
      });
    }
    var state = {
      name: name,
      params: params || {},
      loading: true,
      trigger: opts.trigger || document.activeElement,
      el: null,
      instance: null,
      reason: 'cancelled'
    };
    modalState[layer] = state;
    return fetchModal(name, params).then(function (html) {
      if (html === null) {
        modalState[layer] = null;
        return null;
      }
      target.innerHTML = html;
      var el = target.querySelector('.modal');
      if (!el) {
        target.innerHTML = '';
        modalState[layer] = null;
        return null;
      }
      state.el = el;
      state.loading = false;
      if (layer === 'confirm') raiseConfirmLayer(el);
      el.addEventListener('shown.bs.modal', function () {
        var focusTarget = el.querySelector('[autofocus]');
        if (focusTarget) focusTarget.focus();
        el.dispatchEvent(new CustomEvent('modal:shown', { bubbles: true, detail: modalDetail(state, layer) }));
      }, { once: true });
      el.addEventListener('hide.bs.modal', function () {
        el.dispatchEvent(new CustomEvent('modal:hide', { bubbles: true, detail: modalDetail(state, layer) }));
      }, { once: true });
      el.addEventListener('hidden.bs.modal', function () {
        var detail = modalDetail(state, layer);
        state.instance.dispose();
        target.innerHTML = '';
        modalState[layer] = null;
        if (modalState.page && modalState.page.el) document.body.classList.add('modal-open');
        document.dispatchEvent(new CustomEvent('modal:result', { detail: detail }));
        document.dispatchEvent(new CustomEvent('modal:hidden', { detail: detail }));
        if (state.trigger && state.trigger.focus && document.contains(state.trigger)) state.trigger.focus();
      }, { once: true });
      state.instance = bootstrap.Modal.getOrCreateInstance(el);
      el.dispatchEvent(new CustomEvent('modal:show', { bubbles: true, detail: modalDetail(state, layer) }));
      state.instance.show();
      return el;
    });
  }

  function closeModal(reason, layer) {
    if (!layer) layer = modalState.confirm ? 'confirm' : 'page';
    var state = modalState[layer];
    if (!state || !state.instance) return;
    state.reason = reason || 'cancelled';
    state.instance.hide();
  }

  function swapModalContent(layer, html) {
    var state = modalState[layer];
    if (!state || !state.el) return false;
    var holder = document.createElement('div');
    holder.innerHTML = html;
    var fresh = holder.querySelector('.modal-content');
    var current = state.el.querySelector('.modal-content');
    if (!fresh || !current) return false;
    current.replaceWith(fresh);
    state.el.dispatchEvent(new CustomEvent('modal:shown', { bubbles: true, detail: modalDetail(state, layer) }));
    return true;
  }

  function refreshModal(layer) {
    layer = layer || 'page';
    var state = modalState[layer];
    if (!state || !state.el) return Promise.resolve(false);
    return fetchModal(state.name, state.params).then(function (html) {
      if (html === null) return false;
      return swapModalContent(layer, html);
    });
  }

  function currentModal(layer) {
    var state = modalState[layer || 'page'];
    return state && state.el ? { name: state.name, params: state.params, element: state.el } : null;
  }

  window.Modal = { open: openModal, close: closeModal, refresh: refreshModal, current: currentModal };

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-modal-open]');
    if (!trigger) return;
    e.preventDefault();
    var params = {};
    Array.prototype.forEach.call(trigger.attributes, function (attr) {
      if (attr.name.indexOf('data-') !== 0 || attr.name === 'data-modal-open' || attr.name.indexOf('data-bs-') === 0) return;
      params[attr.name.slice(5).replace(/-/g, '_')] = attr.value;
    });
    openModal(trigger.getAttribute('data-modal-open'), params, { trigger: trigger.closest('.menu') ? document.activeElement : trigger });
  });

  document.addEventListener('click', function (e) {
    var dismiss = e.target.closest('[data-modal-dismiss]');
    if (!dismiss) return;
    e.preventDefault();
    var layer = dismiss.closest('#confirmTarget') ? 'confirm' : 'page';
    closeModal('cancelled', layer);
  });

  window.showConfirmModal = function (opts) {
    opts = opts || {};
    var variant = (opts.confirmClass || 'btn-danger').replace(/^btn-/, '');
    var message = opts.bodyText || (opts.body ? stripHtml(opts.body) : gettext('Are you sure?'));
    var settled = false;
    function onResult(e) {
      if (e.detail.layer !== 'confirm') return;
      document.removeEventListener('modal:result', onResult);
      if (settled) return;
      settled = true;
      if (opts.onCancel) opts.onCancel();
    }
    openModal('confirm', {
      title: opts.title || gettext('Confirm'),
      message: message,
      confirm_label: opts.confirmText || gettext('Confirm'),
      variant: variant
    }, { layer: 'confirm' }).then(function (el) {
      if (!el) {
        if (opts.onCancel) opts.onCancel();
        return;
      }
      document.addEventListener('modal:result', onResult);
      var button = el.querySelector('[data-modal-confirm]');
      if (button) {
        button.addEventListener('click', function () {
          settled = true;
          closeModal('confirmed', 'confirm');
          if (opts.onConfirm) opts.onConfirm();
        });
      }
    });
  };

  document.addEventListener('submit', function (e) {
    var form = e.target;
    var message = form.getAttribute && form.getAttribute('data-confirm');
    if (!message) return;
    e.preventDefault();
    window.showConfirmModal({
      title: form.getAttribute('data-confirm-title') || gettext('Confirm'),
      bodyText: message,
      confirmText: form.getAttribute('data-confirm-button') || gettext('Confirm'),
      confirmClass: form.getAttribute('data-confirm-class') || 'btn-danger',
      onConfirm: function () { form.submit(); }
    });
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.hasAttribute || !form.hasAttribute('data-modal-form')) return;
    e.preventDefault();
    var layer = form.closest('#confirmTarget') ? 'confirm' : 'page';
    var data = new FormData(form);
    if (e.submitter && e.submitter.name) data.append(e.submitter.name, e.submitter.value);
    var buttons = form.querySelectorAll('button[type="submit"]');
    buttons.forEach(function (button) { button.disabled = true; });
    fetch(form.getAttribute('action') || window.location.href, {
      method: 'POST',
      body: data,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    }).then(function (response) {
      var target = redirectTarget(response);
      if (target) {
        window.location.href = target;
        return;
      }
      if (response.status === 422) {
        return response.text().then(function (html) {
          if (!swapModalContent(layer, html)) window.location.reload();
        });
      }
      if (response.ok) {
        window.location.reload();
        return;
      }
      buttons.forEach(function (button) { button.disabled = false; });
      window.showToast(gettext('The form could not be submitted.'), 'danger');
    }).catch(function () {
      buttons.forEach(function (button) { button.disabled = false; });
      window.showToast(gettext('The form could not be submitted.'), 'danger');
    });
  });

  document.addEventListener('change', function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute('data-autosubmit') && e.target.form) e.target.form.submit();
  });

  if (document.getElementById('sidebar')) {
    var seenNotificationIds = {};
    var notificationStream = new EventSource('/api/notifications/stream/');

    notificationStream.onmessage = function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (e) { return; }

      if (data.id && seenNotificationIds[data.id]) return;
      if (data.id) seenNotificationIds[data.id] = true;

      var badge = document.getElementById('notifBadge');
      if (badge && typeof data.unread_count === 'number') {
        badge.textContent = data.unread_count;
        badge.style.display = data.unread_count > 0 ? '' : 'none';
      }

      if (window.showToast) {
        window.showToast(data.message, 'info');
      }
    };
  }
})();
