from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import (
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    TraceabilityLinkFactory,
)
from apps.projects.models import Attachment


class ItemDetailQueryCountTests(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item = ItemFactory(project=self.project, section=self.section, item_id='REQ-001', created_by=self.user, order=1)
        self.client.force_login(self.user)
        self.url = reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key})

    def attach(self, n):
        for k in range(n):
            uploader = UserFactory()
            attachment = Attachment(item=self.item, filename=f'file-{k}.txt', file_size=1, uploaded_by=uploader)
            attachment.file.save(f'file-{k}.txt', ContentFile(b'x'), save=True)

    def relate(self, n):
        for _ in range(n):
            self.counter = getattr(self, 'counter', 9) + 1
            k = self.counter
            other = ItemFactory(project=self.project, section=self.section, item_id=f'REQ-{k:03d}', created_by=UserFactory(), order=k)
            TraceabilityLinkFactory(source_item=self.item, target_item=other, link_type='related-to', created_by=self.user)
            TraceabilityLinkFactory(source_item=other, target_item=self.item, link_type='traces-to', created_by=self.user)
            CommentFactory(item=self.item, author=UserFactory(), text=f'Comment {k}')

    def queries(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return len(ctx), response.json()

    def test_the_query_count_does_not_grow_with_attachments_comments_and_links(self):
        self.attach(1)
        self.relate(1)
        small, _ = self.queries()
        self.attach(6)
        self.relate(5)
        large, payload = self.queries()
        self.assertEqual(large, small)
        self.assertEqual(len(payload['attachments']), 7)
        self.assertEqual(len(payload['comments']), 6)
        self.assertEqual(len(payload['outgoing_links']), 6)
        self.assertEqual(len(payload['incoming_links']), 6)
        self.assertTrue(all(a['uploaded_by_name'] for a in payload['attachments']))
