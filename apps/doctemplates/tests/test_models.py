from django.test import TestCase

from apps.doctemplates.factories import TemplateFactory, TemplateSectionFactory


class TemplateModelTest(TestCase):

    def test_item_id_prefix(self):
        test_cases = [
            ('requirements', 'REQ-'),
            ('architecture', 'ARC-'),
            ('testcases', 'TC-'),
            ('risk', 'RSK-'),
            ('custom', 'ITEM-'),
        ]
        for doc_type, prefix in test_cases:
            tmpl = TemplateFactory(doc_type=doc_type)
            self.assertEqual(tmpl.item_id_prefix, prefix)

    def test_section_count(self):
        tmpl = TemplateFactory()
        self.assertEqual(tmpl.section_count, 0)
        TemplateSectionFactory(template=tmpl, number='100')
        TemplateSectionFactory(template=tmpl, number='101')
        self.assertEqual(tmpl.section_count, 2)

    def test_ordering(self):
        builtin = TemplateFactory(is_builtin=True, name='Builtin')
        custom = TemplateFactory(is_builtin=False, name='Custom')
        from apps.doctemplates.models import Template
        templates = list(Template.objects.filter(pk__in=[builtin.pk, custom.pk]))
        self.assertTrue(templates[0].is_builtin)
