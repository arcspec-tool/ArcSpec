import importlib
from contextlib import redirect_stdout
from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.core.management import CommandError, call_command
from django.db.models import Count
from django.test import TestCase
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.models import User
from apps.doctemplates.models import Template
from apps.notifications.models import AuditLog, Notification
from apps.projects.models import Item, Project, ProjectVersion, Tag

MIGRATION = importlib.import_module('apps.doctemplates.migrations.0001_squashed')
TAG_MIGRATION = importlib.import_module('apps.projects.migrations.0001_squashed')

CC_BY_SA = 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)'

EXPECTED = {
    'Software Requirements Specification': (1, 'requirements', 18, 4, 'Based on IEEE 830-1998'),
    'OWASP ASVS 5.0': (2, 'requirements', 97, 2, CC_BY_SA),
    'arc42 Architecture Documentation': (3, 'architecture', 24, 0, CC_BY_SA),
    'Software Test Documentation': (4, 'testcases', 34, 3, 'based on IEEE 829-1998'),
    'NIST SP 800-30 Risk Assessment': (5, 'risk', 29, 0, '800-30'),
    'GDPR Compliance Documentation': (6, 'custom', 52, 2, 'Regulation (EU) 2016/679'),
    'NIS2 Compliance Documentation': (7, 'custom', 31, 2, 'Directive (EU) 2022/2555'),
    'EU AI Act Compliance Documentation': (8, 'custom', 46, 2, 'Regulation (EU) 2024/1689'),
}

def run_migration():
    with redirect_stdout(StringIO()) as output:
        MIGRATION.add_builtin_templates(apps, None)
    return output.getvalue()


def totals():
    return (
        Template.objects.count(),
        sum(t.sections.count() for t in Template.objects.all()),
        sum(t.attributes.count() for t in Template.objects.all()),
    )


class BuiltinTemplatesMigrationTest(TestCase):

    def test_the_eight_builtin_templates_exist_after_migrate(self):
        builtins = Template.objects.filter(is_builtin=True)
        self.assertEqual(sorted(builtins.values_list('name', flat=True)), sorted(EXPECTED))
        for template in builtins:
            order, doc_type, sections, attributes, attribution = EXPECTED[template.name]
            self.assertTrue(template.is_global, template.name)
            self.assertIsNone(template.created_by, template.name)
            self.assertEqual(template.display_order, order, template.name)
            self.assertEqual(template.doc_type, doc_type, template.name)
            self.assertEqual(template.sections.count(), sections, template.name)
            self.assertEqual(template.attributes.count(), attributes, template.name)
            self.assertIn(attribution, template.description, template.name)

    def test_section_parents_follow_the_numbering(self):
        for template in Template.objects.filter(is_builtin=True):
            by_number = {section.number: section for section in template.sections.all()}
            for number, section in by_number.items():
                parent_number = number.rpartition('.')[0]
                expected_parent = by_number.get(parent_number) if parent_number else None
                self.assertEqual(section.parent, expected_parent, f'{template.name} {number}')

    def test_running_the_migration_again_changes_nothing(self):
        before = totals()
        keys = set(Template.objects.values_list('public_key', flat=True))
        output = run_migration()
        self.assertEqual(totals(), before)
        self.assertEqual(set(Template.objects.values_list('public_key', flat=True)), keys)
        self.assertIn('Built-in templates: 0 created', output)

    def test_migration_data_matches_the_expected_counts(self):
        specs = {spec['name']: spec for spec in MIGRATION.BUILTIN_TEMPLATES}
        self.assertEqual(set(specs), set(EXPECTED))
        for name, spec in specs.items():
            order, doc_type, sections, attributes, attribution = EXPECTED[name]
            self.assertEqual(spec['display_order'], order, name)
            self.assertEqual(spec['doc_type'], doc_type, name)
            self.assertEqual(len(spec['sections']), sections, name)
            self.assertEqual(len(spec['attributes']), attributes, name)
            self.assertIn(attribution, spec['description'], name)
            numbers = [number for number, _, _ in spec['sections']]
            self.assertEqual(len(numbers), len(set(numbers)), name)
            for number, title, description in spec['sections']:
                self.assertTrue(title.strip(), f'{name} {number}')
                self.assertTrue(description.strip(), f'{name} {number}')


class TagPresetsMigrationTest(TestCase):

    def test_the_ten_presets_exist_after_migrate(self):
        presets = Tag.objects.filter(project__isnull=True, is_preset=True)
        self.assertEqual(presets.count(), len(TAG_MIGRATION.TAG_PRESETS))
        self.assertEqual(
            sorted(presets.values_list('name', flat=True)),
            sorted(name for name, _ in TAG_MIGRATION.TAG_PRESETS),
        )

    def test_running_the_migration_again_creates_nothing(self):
        before = Tag.objects.count()
        TAG_MIGRATION.create_tag_presets(apps, None)
        self.assertEqual(Tag.objects.count(), before)


class SeedDataTest(TestCase):

    def test_seed_data_fills_an_empty_database_with_history_in_the_past(self):
        builtins_before = Template.objects.filter(is_builtin=True).count()
        presets_before = Tag.objects.filter(is_preset=True).count()
        call_command('seed_data', stdout=StringIO())
        self.assertEqual(Template.objects.filter(is_builtin=True).count(), builtins_before)
        self.assertEqual(Tag.objects.filter(is_preset=True).count(), presets_before)
        self.assertEqual(dict(Project.objects.values_list('name', 'status')), {
            'Telephone Booking Process': 'archived',
            'Online Booking System': 'active',
            'Patient Data Protection Record': 'active',
            'Online Booking System Test Plan': 'in-review',
            'Booking Portal Security Review': 'in-review',
            'Online Booking System Architecture': 'draft',
        })
        self.assertEqual(Item.objects.count(), 58)
        booking = Project.objects.get(name='Online Booking System')
        self.assertEqual(booking.next_item_number, 28)
        self.assertEqual(booking.items.order_by('-item_id').first().item_id, 'REQ-027')
        self.assertEqual(User.objects.count(), 7)
        self.assertEqual(User.objects.filter(is_active=False).count(), 1)
        now = timezone.now()
        self.assertFalse(AuditLog.objects.filter(created_at__gt=now - timedelta(minutes=4)).exists())
        self.assertFalse(ProjectVersion.objects.filter(changed_at__gt=now - timedelta(minutes=4)).exists())
        self.assertFalse(Notification.objects.filter(created_at__gt=now - timedelta(minutes=4)).exists())

    def test_seed_data_numbers_each_project_version_once(self):
        call_command('seed_data', stdout=StringIO())
        repeated = ProjectVersion.objects.values('project', 'version_number').annotate(n=Count('pk')).filter(n__gt=1)
        self.assertEqual(list(repeated), [])

    def test_seed_data_refuses_a_database_that_has_users(self):
        UserFactory()
        with self.assertRaises(CommandError):
            call_command('seed_data', stdout=StringIO())
        self.assertEqual(Project.objects.count(), 0)
