(function () {
    'use strict';

    function cloneTemplate(root, id) {
        var tpl = root.querySelector('#' + id);
        return tpl && tpl.content ? tpl.content.firstElementChild.cloneNode(true) : null;
    }

    function newSectionItem(root, title) {
        var item = cloneTemplate(root, 'sectionItemTemplate');
        if (!item) return null;
        var input = item.querySelector('.section-name-input');
        if (input) input.value = title;
        return item;
    }

    function initSectionTree(root) {
        var addBtn = root.querySelector('#addSectionBtn');
        var tree = root.querySelector('#sectionTree');
        if (!addBtn || !tree) return;

        addBtn.addEventListener('click', function () {
            var item = newSectionItem(root, gettext('Section name'));
            if (!item) return;
            tree.appendChild(item);
            renumberSections(tree);
            item.querySelector('.section-name-input').focus();
            item.querySelector('.section-name-input').select();
        });

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
                renumberSections(tree);
                return;
            }

            if (action === 'add-child') {
                var children = sectionItem.querySelector(':scope > .section-children');
                if (!children) {
                    children = document.createElement('div');
                    children.className = 'section-children';
                    sectionItem.appendChild(children);
                }

                var sub = newSectionItem(root, gettext('New section'));
                if (!sub) return;
                children.appendChild(sub);
                renumberSections(tree);
                sub.querySelector('.section-name-input').focus();
                sub.querySelector('.section-name-input').select();
                return;
            }

            if (action === 'up') {
                var prev = sectionItem.previousElementSibling;
                while (prev && !prev.classList.contains('section-item')) prev = prev.previousElementSibling;
                if (prev) {
                    sectionItem.parentNode.insertBefore(sectionItem, prev);
                    renumberSections(tree);
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
                    renumberSections(tree);
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
                renumberSections(tree);
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

                renumberSections(tree);
                return;
            }
        });

        tree.addEventListener('click', function (e) {
            var toggle = e.target.closest('.section-toggle');
            if (!toggle) return;
            toggle.classList.toggle('collapsed');
            var children = toggle.closest('.section-item').querySelector('.section-children');
            if (children) {
                children.style.display = toggle.classList.contains('collapsed') ? 'none' : '';
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
                renumberSections(tree);
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }

    function renumberSections(root) {
        var topItems = root.querySelectorAll(':scope > .section-item');
        for (var i = 0; i < topItems.length; i++) {
            var num = (i + 1) + '';
            var numEl = topItems[i].querySelector(':scope > .section-item-content .section-number');
            if (numEl) numEl.textContent = num;
            var childContainer = topItems[i].querySelector(':scope > .section-children');
            if (childContainer) {
                renumberChildren(childContainer, num);
            }
        }
    }

    function renumberChildren(container, parentNum) {
        var items = container.querySelectorAll(':scope > .section-item');
        for (var j = 0; j < items.length; j++) {
            var subNum = parentNum + '.' + (j + 1);
            var numEl = items[j].querySelector(':scope > .section-item-content .section-number');
            if (numEl) numEl.textContent = subNum;
            var childContainer = items[j].querySelector(':scope > .section-children');
            if (childContainer) {
                renumberChildren(childContainer, subNum);
            }
        }
    }

    function initSectionSerializer(root) {
        var editorForm = root.querySelector('#templateEditorForm');
        if (!editorForm) return;
        editorForm.addEventListener('submit', function () {
            var oldInputs = editorForm.querySelectorAll('.section-hidden-input');
            oldInputs.forEach(function (el) { el.remove(); });

            var tree = root.querySelector('#sectionTree');
            if (!tree) return;

            var allItems = tree.querySelectorAll('.section-item');
            for (var r = 0; r < allItems.length; r++) {
                allItems[r].setAttribute('data-ref', 'ref-' + r);
            }

            var idx = 0;
            function addHidden(name, value) {
                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = name;
                input.value = value;
                input.className = 'section-hidden-input';
                editorForm.appendChild(input);
            }

            function serializeLevel(container, parentRef) {
                var items = container.querySelectorAll(':scope > .section-item');
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    var numberEl = item.querySelector(':scope > .section-item-content .section-number');
                    var titleEl = item.querySelector(':scope > .section-item-content .section-name-input');
                    var sectionId = item.getAttribute('data-section-id') || '';
                    var ref = item.getAttribute('data-ref') || '';
                    var descEl = item.querySelector(':scope > .section-desc-wrapper .section-desc-input');

                    addHidden('sections-' + idx + '-number', numberEl ? numberEl.textContent : '');
                    addHidden('sections-' + idx + '-title', titleEl ? titleEl.value : '');
                    addHidden('sections-' + idx + '-description', descEl ? descEl.value : '');
                    addHidden('sections-' + idx + '-order', idx);
                    addHidden('sections-' + idx + '-parent_ref', parentRef);
                    addHidden('sections-' + idx + '-ref', ref);
                    addHidden('sections-' + idx + '-id', sectionId);

                    idx++;

                    var childContainer = item.querySelector(':scope > .section-children');
                    if (childContainer) {
                        serializeLevel(childContainer, ref);
                    }
                }
            }

            serializeLevel(tree, '');

            var totalForms = editorForm.querySelector('[name="sections-TOTAL_FORMS"]');
            if (totalForms) totalForms.value = idx;
        });
    }

    function initCustomAttributes(root) {
        var addBtn = root.querySelector('#addAttributeBtn');
        var container = root.querySelector('#customAttributes');
        if (!addBtn || !container) return;

        addBtn.addEventListener('click', function () {
            var row = cloneTemplate(root, 'attributeRowTemplate');
            if (!row) return;
            container.appendChild(row);
            row.querySelector('input[name="attr_name[]"]').focus();
        });

        container.addEventListener('click', function (e) {
            var remove = e.target.closest('.attribute-row-custom [data-attribute-action="remove"]');
            if (remove) remove.closest('.attribute-row-custom').remove();
        });

        container.addEventListener('change', function (e) {
            if (!e.target.classList.contains('attr-type-select')) return;
            var row = e.target.closest('.attribute-row-custom');
            var wrapper = row ? row.querySelector('.attr-options-wrapper') : null;
            if (!wrapper) return;
            wrapper.style.display = (e.target.value === 'dropdown' || e.target.value === 'multiselect') ? '' : 'none';
        });
    }

    document.addEventListener('modal:shown', function (e) {
        if (!e.detail || e.detail.name !== 'template_editor') return;
        initSectionTree(e.target);
        initSectionSerializer(e.target);
        initCustomAttributes(e.target);
    });
})();
