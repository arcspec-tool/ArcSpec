from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import (
    ItemAttributeValueFactory,
    ItemFactory,
    ProjectAttributeFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)
from apps.projects.models import attribute_user_names


class AttributeDisplayValueTests(TestCase):

    def setUp(self):
        self.user = UserFactory(display_name='Reviewer One')
        self.project = ProjectFactory()
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        self.section = SectionFactory(project=self.project, number='1', title='Intro')
        self.item = ItemFactory(project=self.project, section=self.section, item_id='REQ-001', created_by=self.user)
        self.reviewer = ProjectAttributeFactory(project=self.project, name='Reviewer', field_type='user')
        self.safety = ProjectAttributeFactory(project=self.project, name='Safety', field_type='boolean')
        self.note = ProjectAttributeFactory(project=self.project, name='Note', field_type='text')
        ItemAttributeValueFactory(item=self.item, attribute=self.reviewer, value=str(self.user.pk))
        ItemAttributeValueFactory(item=self.item, attribute=self.safety, value='false')
        ItemAttributeValueFactory(item=self.item, attribute=self.note, value='plain')

    def test_display_value_per_field_type(self):
        self.assertEqual(self.reviewer.display_value(str(self.user.pk)), 'Reviewer One')
        self.assertEqual(self.reviewer.display_value(str(self.user.pk), {str(self.user.pk): 'Mapped'}), 'Mapped')
        self.assertEqual(self.reviewer.display_value('999999'), '999999')
        self.assertEqual(self.reviewer.display_value(''), '')
        self.assertEqual(self.safety.display_value('true'), 'Yes')
        self.assertEqual(self.safety.display_value('false'), 'No')
        self.assertEqual(self.note.display_value('plain'), 'plain')

    def test_user_names_cover_every_user_value_of_the_project(self):
        other = ProjectFactory()
        other_attr = ProjectAttributeFactory(project=other, name='Owner', field_type='user')
        other_item = ItemFactory(project=other, section=SectionFactory(project=other, number='1'), item_id='REQ-001')
        ItemAttributeValueFactory(item=other_item, attribute=other_attr, value='not-a-number')
        self.assertEqual(attribute_user_names(self.project), {str(self.user.pk): 'Reviewer One'})
        self.assertEqual(attribute_user_names(other), {})

    def test_the_items_api_carries_display_values(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('api_item_list', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        items = payload['results'] if isinstance(payload, dict) else payload
        values = {av['attribute_name']: av['display_value'] for av in items[0]['attribute_values']}
        self.assertEqual(values, {'Reviewer': 'Reviewer One', 'Safety': 'No', 'Note': 'plain'})
        response = self.client.get(reverse('api_item_detail', kwargs={'slug': self.project.slug, 'public_key': self.item.public_key}))
        self.assertEqual(response.status_code, 200)
        values = {av['attribute_name']: av['display_value'] for av in response.json()['attribute_values']}
        self.assertEqual(values['Reviewer'], 'Reviewer One')
