import html
import json
from datetime import timedelta

from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone
from django.utils.safestring import SafeString

from apps.core.templatetags.core_tags import status_badge, priority_badge, time_ago, to_json


class ToJsonFilterTest(TestCase):

    def test_the_filter_is_plain_text_that_autoescaping_encodes(self):
        value = {'q': 'a\'b<c"d'}
        self.assertNotIsInstance(to_json(value), SafeString)
        rendered = Template("{% load core_tags %}<b data-filters='{{ v|to_json }}'></b>").render(Context({'v': value}))
        self.assertEqual(rendered, "<b data-filters='{&quot;q&quot;: &quot;a&#x27;b&lt;c\\&quot;d&quot;}'></b>")
        self.assertEqual(json.loads(html.unescape(rendered[len("<b data-filters='"):-len("'></b>")])), value)


class StatusBadgeTest(TestCase):

    def test_unknown(self):
        result = status_badge('unknown')
        self.assertEqual(result['label'], 'unknown')
        self.assertEqual(result['css_class'], 'status-other')

    def test_renders_a_status_pill(self):
        rendered = Template('{% load core_tags %}{% status_badge "in-review" %}').render(Context())
        self.assertEqual(rendered.strip(), '<span class="status-pill status-in-review">In Review</span>')

    def test_account_and_visibility_states(self):
        self.assertEqual(status_badge('inactive'), {'label': 'Inactive', 'css_class': 'status-archived'})
        self.assertEqual(status_badge('builtin'), {'label': 'Built-in', 'css_class': 'status-draft'})
        self.assertEqual(status_badge('public'), {'label': 'Public', 'css_class': 'status-active'})
        self.assertEqual(status_badge('private'), {'label': 'Private', 'css_class': 'status-other'})


class PriorityBadgeTest(TestCase):

    def test_low_and_unknown(self):
        self.assertEqual(priority_badge('low'), {'label': 'Low', 'css_class': 'priority-low'})
        self.assertEqual(priority_badge('urgent'), {'label': 'urgent', 'css_class': 'priority-other'})

    def test_rendered_label_carries_the_flag_and_the_class(self):
        from django.template import Context, Template
        html = Template('{% load core_tags %}{% priority_badge "high" %}').render(Context())
        self.assertIn('<span class="priority-label priority-high"><i class="bi bi-flag-fill" aria-hidden="true"></i>High</span>', html)


class SystemRoleBadgeTest(TestCase):

    def test_renders_a_pill(self):
        rendered = Template('{% load core_tags %}{% system_role_badge "viewer" %}').render(Context())
        self.assertEqual(rendered.strip(), '<span class="status-pill role-viewer">Viewer</span>')


class TimeAgoFilterTest(TestCase):

    def test_under_a_minute_reads_just_now(self):
        self.assertEqual(time_ago(timezone.now() - timedelta(seconds=20)), 'just now')

    def test_older_values_use_the_short_unit(self):
        self.assertEqual(time_ago(timezone.now() - timedelta(minutes=5, seconds=10)), '5min ago')
        self.assertEqual(time_ago(timezone.now() - timedelta(days=2, hours=1)), '2d ago')

    def test_a_missing_value_renders_nothing(self):
        self.assertEqual(time_ago(None), '')
