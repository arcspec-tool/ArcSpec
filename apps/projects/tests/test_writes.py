from django.core import mail
from django.db import transaction
from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.projects.factories import OwnedProjectFactory, ProjectMembershipFactory, SectionFactory
from apps.projects.writes import create_item


class CreateItemTests(TestCase):

    def setUp(self):
        self.owner = UserFactory()
        self.project = OwnedProjectFactory(created_by=self.owner)
        self.member = UserFactory()
        ProjectMembershipFactory(project=self.project, user=self.member, role='editor')
        self.section = SectionFactory(project=self.project)

    def test_an_item_create_that_rolls_back_sends_no_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            create_item(self.project, self.owner, {'section': self.section, 'text': '<p>Kept</p>'})
        self.assertEqual([message.to for message in mail.outbox], [[self.member.email]])
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    create_item(self.project, self.owner, {'section': self.section, 'text': '<p>Lost</p>'})
                    raise RuntimeError('undo')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(list(self.project.items.values_list('text', flat=True)), ['<p>Kept</p>'])
