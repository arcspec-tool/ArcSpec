import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ItemFactory, OwnedProjectFactory, SectionFactory


class ArchivedProjectReadOnlyTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.project = OwnedProjectFactory(created_by=self.user, status='archived')
        self.section = SectionFactory(project=self.project)
        self.item = ItemFactory(project=self.project, section=self.section, created_by=self.user, text='Kept')
        self.client.force_login(self.user)

    def test_changes_to_an_archived_project_are_refused(self):
        slug = self.project.slug
        requests = (
            ('post', reverse('api_item_list', kwargs={'slug': slug}), {'section': self.section.pk, 'text': 'New', 'status': 'draft', 'priority': 'medium'}),
            ('patch', reverse('api_item_inline_edit', kwargs={'slug': slug, 'public_key': self.item.public_key}), {'field': 'text', 'value': 'Changed'}),
            ('post', reverse('api_comment_list', kwargs={'slug': slug, 'item_key': self.item.public_key}), {'text': 'Hello'}),
            ('post', reverse('api_collaborator_invite', kwargs={'slug': slug}), {'email': 'someone@example.com', 'role': 'editor'}),
            ('post', reverse('section_create', kwargs={'slug': slug}), {'title': 'New section'}),
        )
        for method, url, payload in requests:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, json.dumps(payload), content_type='application/json')
                self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.text, 'Kept')
        self.assertEqual(self.project.items.count(), 1)
        self.assertEqual(self.project.sections.count(), 1)

    def test_archived_project_cannot_be_edited_through_the_edit_form(self):
        response = self.client.post(reverse('project_update', kwargs={'slug': self.project.slug}), {
            'name': 'Renamed', 'description': '', 'status': 'active', 'color': self.project.color,
        })
        self.assertEqual(response.status_code, 403)

    def test_archived_project_page_offers_its_admin_no_item_menu_and_no_comment_box(self):
        for status, offered in (('active', True), ('archived', False)):
            with self.subTest(status=status):
                self.project.status = status
                self.project.save(update_fields=['status'])
                response = self.client.get(reverse('project_detail', kwargs={'slug': self.project.slug}))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertEqual('id="itemMenu"' in html, offered)
                self.assertEqual('id="commentInput"' in html, offered)
