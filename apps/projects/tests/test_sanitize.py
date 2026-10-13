from django.test import TestCase

from apps.projects.sanitize import sanitize_rich_text


class SanitizeRichTextTests(TestCase):

    def test_strips_script_tag(self):
        html = '<p>Hello</p><script>alert("xss")</script>'
        result = sanitize_rich_text(html)
        self.assertNotIn('<script', result)
        self.assertIn('<p>Hello</p>', result)

    def test_keeps_basic_formatting(self):
        html = '<p><strong>Bold</strong> <em>italic</em> <u>underline</u> <s>strike</s></p>'
        result = sanitize_rich_text(html)
        self.assertIn('<strong>Bold</strong>', result)
        self.assertIn('<em>italic</em>', result)
        self.assertIn('<u>underline</u>', result)
        self.assertIn('<s>strike</s>', result)

    def test_keeps_lists(self):
        html = '<ul><li>A</li><li>B</li></ul><ol><li>1</li></ol>'
        result = sanitize_rich_text(html)
        self.assertIn('<ul>', result)
        self.assertIn('<li>A</li>', result)
        self.assertIn('<ol>', result)

    def test_strips_headings(self):
        html = '<h1>Title</h1><h2>Sub</h2><h3>Sub-sub</h3>'
        result = sanitize_rich_text(html)
        self.assertNotIn('<h1>', result)
        self.assertNotIn('<h2>', result)
        self.assertNotIn('<h3>', result)
        self.assertIn('Title', result)

    def test_keeps_table(self):
        html = '<table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>'
        result = sanitize_rich_text(html)
        self.assertIn('<table>', result)
        self.assertIn('<thead>', result)
        self.assertIn('<tbody>', result)
        self.assertIn('<th>A</th>', result)
        self.assertIn('<td>1</td>', result)

    def test_keeps_table_colspan_rowspan(self):
        html = '<table><tr><td colspan="2" rowspan="3">Wide</td></tr></table>'
        result = sanitize_rich_text(html)
        self.assertIn('colspan="2"', result)
        self.assertIn('rowspan="3"', result)

    def test_strips_style_attribute(self):
        html = '<p style="color:red">Text</p>'
        result = sanitize_rich_text(html)
        self.assertNotIn('style', result)
        self.assertIn('<p>Text</p>', result)

    def test_strips_onclick(self):
        html = '<p onclick="alert(1)">Click</p>'
        result = sanitize_rich_text(html)
        self.assertNotIn('onclick', result)

    def test_strips_img_tag(self):
        html = '<p>Text</p><img src="evil.jpg" onerror="alert(1)">'
        result = sanitize_rich_text(html)
        self.assertNotIn('<img', result)

    def test_empty_string(self):
        self.assertEqual(sanitize_rich_text(''), '')

    def test_none_input(self):
        self.assertIsNone(sanitize_rich_text(None))

    def test_strips_div_tag(self):
        html = '<div>Content</div>'
        result = sanitize_rich_text(html)
        self.assertNotIn('<div', result)
        self.assertIn('Content', result)

    def test_strips_iframe(self):
        html = '<iframe src="evil.com"></iframe><p>Safe</p>'
        result = sanitize_rich_text(html)
        self.assertNotIn('<iframe', result)
        self.assertIn('<p>Safe</p>', result)
