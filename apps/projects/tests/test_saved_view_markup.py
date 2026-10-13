import html
import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import ProjectFactory, ProjectMembershipFactory, SavedViewFactory


class SavedViewMarkupTest(TestCase):

    def test_filter_values_cannot_break_out_of_the_attribute(self):
        user = UserFactory()
        project = ProjectFactory(created_by=user)
        ProjectMembershipFactory(project=project, user=user, role='admin')
        filters = {'status': "draft' onmouseover='x", 'tag': '<b>'}
        SavedViewFactory(project=project, user=user, name='Hostile', filters=filters)
        self.client.force_login(user)
        response = self.client.get(reverse('project_detail', kwargs={'slug': project.slug}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("onmouseover='x", content)
        attribute = re.search(r"data-filters='([^']*)'", content).group(1)
        self.assertEqual(json.loads(html.unescape(attribute)), filters)
