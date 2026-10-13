from django.test import TestCase

from apps.accounts.factories import UserFactory
from apps.projects.factories import (
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)


class GlobalSearchViewTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_unauthenticated_returns_403(self):
        self.client.logout()
        response = self.client.get('/api/projects/search/?q=test')
        self.assertEqual(response.status_code, 403)

    def test_short_query_returns_empty(self):
        response = self.client.get('/api/projects/search/?q=a')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['projects'], [])
        self.assertEqual(data['items'], [])

    def test_search_finds_project_by_name(self):
        project = ProjectFactory(name='Alpha Testing Project')
        ProjectMembershipFactory(project=project, user=self.user, role='editor')
        response = self.client.get('/api/projects/search/?q=Alpha')
        data = response.json()
        self.assertEqual(len(data['projects']), 1)
        self.assertEqual(data['projects'][0]['name'], 'Alpha Testing Project')

    def test_search_finds_items(self):
        project = ProjectFactory(name='MyProject')
        ProjectMembershipFactory(project=project, user=self.user, role='editor')
        section = SectionFactory(project=project)
        item = ItemFactory(project=project, section=section, text='Important requirement about security')
        response = self.client.get('/api/projects/search/?q=security')
        data = response.json()
        self.assertEqual(len(data['items']), 1)
        self.assertIn('security', data['items'][0]['text'].lower())

    def test_item_text_separates_paragraphs_and_list_items_with_a_space(self):
        project = ProjectFactory(name='MyProject')
        ProjectMembershipFactory(project=project, user=self.user, role='editor')
        section = SectionFactory(project=project)
        ItemFactory(project=project, section=section, text='<p>Main functions:</p><ul><li>Book slots.</li><li>Cancel slots.</li></ul>')
        response = self.client.get('/api/projects/search/?q=functions')
        self.assertEqual(response.json()['items'][0]['text'], 'Main functions: Book slots. Cancel slots.')

    def test_search_only_returns_user_projects(self):
        other_user = UserFactory()
        project = ProjectFactory(name='Secret Project', created_by=other_user)
        ProjectMembershipFactory(project=project, user=other_user)
        response = self.client.get('/api/projects/search/?q=Secret')
        data = response.json()
        self.assertEqual(len(data['projects']), 0)

    def test_empty_query_returns_empty(self):
        response = self.client.get('/api/projects/search/?q=')
        data = response.json()
        self.assertEqual(data['projects'], [])
        self.assertEqual(data['items'], [])
