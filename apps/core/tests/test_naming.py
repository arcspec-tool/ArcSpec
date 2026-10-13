import re

from django.conf import settings
from django.test import SimpleTestCase

TITLE_BLOCK = re.compile(r'\{% block title %\}(.*?)\{% endblock %\}')
TRANSLATED = re.compile(r'\{% translate "(.*?)" %\}')


class NamingTest(SimpleTestCase):

    def test_every_page_title_ends_in_arcspec(self):
        titles = []
        wrong = []
        for path in sorted((settings.BASE_DIR / 'apps').glob('*/templates/**/*.html')):
            for match in TITLE_BLOCK.finditer(path.read_text(encoding='utf-8')):
                titles.append(match.group(1))
                if not TRANSLATED.sub(r'\1', match.group(1)).endswith('ArcSpec'):
                    wrong.append(f'{path.relative_to(settings.BASE_DIR)}: {match.group(1)}')
        self.assertGreater(len(titles), 0)
        self.assertEqual(wrong, [])
