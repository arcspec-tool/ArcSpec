import re

from django.conf import settings
from django.test import SimpleTestCase

INLINE_HANDLER = re.compile(r'<[^>]*\son[a-z]+\s*=', re.IGNORECASE)
CDN_TAG = re.compile(r'<(?:script|link)\b[^>]*?\b(?:src|href)="(https://cdn\.jsdelivr\.net/[^"]+)"[^>]*>', re.IGNORECASE)
EXACT_VERSION = re.compile(r'^https://cdn\.jsdelivr\.net/npm/[^/@]+@\d+\.\d+\.\d+/')
BROWSER_DIALOG = re.compile(r'(?<![\w.])(?:window\.)?(?:confirm|alert|prompt)\(')


def templates():
    for path in sorted((settings.BASE_DIR / 'apps').glob('*/templates/**/*.html')):
        yield path.relative_to(settings.BASE_DIR), path.read_text(encoding='utf-8')


def scripts():
    for path in sorted((settings.BASE_DIR / 'apps').glob('*/static/js/*.js')):
        yield path.relative_to(settings.BASE_DIR), path.read_text(encoding='utf-8')


class TemplatePolicyTest(SimpleTestCase):

    def test_no_template_carries_an_inline_event_handler(self):
        hits = []
        for relative, text in templates():
            for match in INLINE_HANDLER.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                hits.append(f'{relative}:{line}')
        self.assertEqual(hits, [])

    def test_every_cdn_asset_is_pinned_and_carries_an_integrity_hash(self):
        problems = []
        seen = 0
        for relative, text in templates():
            for match in CDN_TAG.finditer(text):
                seen += 1
                tag, url = match.group(0), match.group(1)
                if not EXACT_VERSION.match(url):
                    problems.append(f'{relative}: {url} is not pinned to an exact version')
                if 'integrity="sha384-' not in tag or 'crossorigin="anonymous"' not in tag:
                    problems.append(f'{relative}: {url} has no integrity hash')
        self.assertEqual(problems, [])
        self.assertGreater(seen, 0)

    def test_no_script_opens_a_browser_dialog(self):
        hits = []
        definitions = []
        for relative, text in list(scripts()) + list(templates()):
            for match in BROWSER_DIALOG.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                hits.append(f'{relative}:{line}')
            if 'window.showConfirmModal = function' in text:
                definitions.append(str(relative))
        self.assertEqual(hits, [])
        self.assertEqual(definitions, ['apps/core/static/js/app.js'])

    def test_sign_out_goes_through_the_sign_out_modal(self):
        base = (settings.BASE_DIR / 'apps/core/templates/base.html').read_text(encoding='utf-8')
        sidebar = (settings.BASE_DIR / 'apps/core/templates/includes/_sidebar.html').read_text(encoding='utf-8')
        holders = [str(relative) for relative, text in templates() if "{% url 'logout' %}" in text]
        self.assertEqual(holders, ['apps/core/templates/modals/_sign_out.html'])
        self.assertIn('data-modal-open="sign_out"', base)
        self.assertIn('data-modal-open="sign_out"', sidebar)

    def test_modal_markup_lives_only_in_the_shell_and_is_fetched_on_demand(self):
        holders = [str(relative) for relative, text in templates() if 'modal fade' in text]
        self.assertEqual(holders, ['apps/core/templates/components/_modal_shell.html'])
        toggles = [str(relative) for relative, text in templates() if 'data-bs-toggle="modal"' in text]
        self.assertEqual(toggles, [])
        bootstrap_users = [str(relative) for relative, text in scripts() if 'bootstrap.Modal' in text or '.bs.modal' in text]
        self.assertEqual(bootstrap_users, ['apps/core/static/js/app.js'])

    def test_every_modal_partial_extends_the_shell_or_is_included_by_one(self):
        from apps.core import modals
        from django.template.loader import get_template
        all_templates = list(templates())
        partials = [(relative, text) for relative, text in all_templates if relative.parent.name == 'modals' and relative.name.startswith('_')]
        self.assertGreater(len(partials), 0)
        for relative, text in partials:
            extends = 'extends "components/_modal_shell.html"' in text
            included = any(relative.name in other for other_relative, other in all_templates if other_relative != relative)
            self.assertTrue(extends or included, f'{relative} neither extends the shell nor is included by a modal')
        for name in modals.names():
            spec = modals.get(name)
            source = get_template(spec.template).template.source
            self.assertIn('extends "components/_modal_shell.html"', source, name)

    def test_the_base_layout_carries_the_modal_targets_and_no_modal(self):
        base = (settings.BASE_DIR / 'apps/core/templates/base.html').read_text(encoding='utf-8')
        self.assertEqual(base.count('id="modalTarget"'), 1)
        self.assertEqual(base.count('id="confirmTarget"'), 1)
        self.assertNotIn('modal fade', base)
        self.assertNotIn('_confirm.html', base)
        holders = [str(relative) for relative, text in templates() if '_confirm.html' in text or '_confirm_modal.html' in text]
        self.assertEqual(holders, [])
