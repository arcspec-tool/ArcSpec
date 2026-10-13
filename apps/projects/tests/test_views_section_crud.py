import json

from django.test import TestCase
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.projects.factories import (
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)
from apps.projects.models import Section


class SectionCreateTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_create_top_level_section(self):
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'New Section',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        section = Section.objects.get(pk=data['section']['id'])
        self.assertEqual(section.title, 'New Section')
        self.assertEqual(section.project, self.project)
        self.assertIsNone(section.parent)

    def test_create_nested_section(self):
        parent = SectionFactory(project=self.project, title='Parent', number='1', order=0)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Child Section',
            'parent_id': parent.pk,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        section = Section.objects.get(pk=data['section']['id'])
        self.assertEqual(section.parent, parent)

    def test_create_section_auto_numbers(self):
        SectionFactory(project=self.project, title='First', number='1', order=0)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        self.client.post(url, data=json.dumps({
            'title': 'Second',
        }), content_type='application/json')
        sections = Section.objects.filter(project=self.project).order_by('order')
        numbers = list(sections.values_list('number', flat=True))
        self.assertEqual(numbers, ['1', '2'])

    def test_create_section_with_description(self):
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Described Section',
            'description': 'This section covers the introduction.',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        section = Section.objects.get(pk=data['section']['id'])
        self.assertEqual(section.description, 'This section covers the introduction.')
        self.assertEqual(data['section']['description'], 'This section covers the introduction.')

    def test_create_section_without_description(self):
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'No Description',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        section = Section.objects.get(pk=data['section']['id'])
        self.assertEqual(section.description, '')

    def test_create_requires_title(self):
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': '',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_parent_from_other_project(self):
        other_project = ProjectFactory()
        other_section = SectionFactory(project=other_project)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Bad Child',
            'parent_id': other_section.pk,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_editor_can_create_section(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Editor Section',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_create_section(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Viewer Section',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_non_member_gets_404(self):
        stranger = UserFactory()
        self.client.force_login(stranger)
        url = reverse('section_create', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'title': 'Stranger Section',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 404)


class SectionUpdateTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')
        self.section = SectionFactory(
            project=self.project, title='Original', number='1', order=0
        )

    def test_rename_section(self):
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'title': 'Renamed Section',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.title, 'Renamed Section')

    def test_move_section_to_new_parent(self):
        parent = SectionFactory(
            project=self.project, title='Parent', number='2', order=1
        )
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'parent_id': parent.pk,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.parent, parent)

    def test_move_section_to_top_level(self):
        parent = SectionFactory(project=self.project, title='Parent', number='1', order=0)
        self.section.parent = parent
        self.section.save()
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'parent_id': None,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertIsNone(self.section.parent)

    def test_update_section_description(self):
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'description': 'Updated description text',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.description, 'Updated description text')
        data = response.json()
        self.assertEqual(data['section']['description'], 'Updated description text')

    def test_update_rejects_empty_title(self):
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'title': '',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_rejects_parent_from_other_project(self):
        other_section = SectionFactory(project=ProjectFactory())
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'parent_id': other_section.pk,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_rejects_self_as_parent(self):
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'parent_id': self.section.pk,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_update_section(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': self.section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'title': 'Hacked',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_section_from_other_project_returns_404(self):
        other_project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=other_project, user=self.user, role='admin')
        other_section = SectionFactory(project=other_project)
        url = reverse('section_update', kwargs={
            'slug': self.project.slug, 'public_key': other_section.public_key,
        })
        response = self.client.post(url, data=json.dumps({
            'title': 'Cross-project',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_update_rejects_two_node_cycle(self):
        a = SectionFactory(project=self.project, title='A', number='1', order=0)
        b = SectionFactory(project=self.project, title='B', number='2', order=1)
        url_a = reverse('section_update', kwargs={'slug': self.project.slug, 'public_key': a.public_key})
        resp = self.client.post(url_a, data=json.dumps({'parent_id': b.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        url_b = reverse('section_update', kwargs={'slug': self.project.slug, 'public_key': b.public_key})
        resp = self.client.post(url_b, data=json.dumps({'parent_id': a.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('circular', resp.json()['errors']['parent_id'][0])

    def test_update_rejects_deep_cycle(self):
        a = SectionFactory(project=self.project, title='A', number='1', order=0)
        b = SectionFactory(project=self.project, title='B', number='2', order=1, parent=a)
        c = SectionFactory(project=self.project, title='C', number='3', order=2, parent=b)
        url_a = reverse('section_update', kwargs={'slug': self.project.slug, 'public_key': a.public_key})
        resp = self.client.post(url_a, data=json.dumps({'parent_id': c.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_allows_valid_reparent(self):
        a = SectionFactory(project=self.project, title='A', number='1', order=0)
        b = SectionFactory(project=self.project, title='B', number='2', order=1)
        c = SectionFactory(project=self.project, title='C', number='3', order=2, parent=a)
        url_c = reverse('section_update', kwargs={'slug': self.project.slug, 'public_key': c.public_key})
        resp = self.client.post(url_c, data=json.dumps({'parent_id': b.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.parent_id, b.pk)


class SectionDeleteTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_delete_empty_section(self):
        section = SectionFactory(project=self.project, title='Empty', number='1', order=0)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': section.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Section.objects.filter(pk=section.pk).exists())

    def test_delete_section_with_items_blocked(self):
        section = SectionFactory(project=self.project, title='Has Items', number='1', order=0)
        ItemFactory(project=self.project, section=section)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': section.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['ok'])
        self.assertTrue(Section.objects.filter(pk=section.pk).exists())

    def test_delete_section_with_child_that_has_items_blocked(self):
        parent = SectionFactory(project=self.project, title='Parent', number='1', order=0)
        child = SectionFactory(
            project=self.project, title='Child', number='1.1', order=1, parent=parent
        )
        ItemFactory(project=self.project, section=child)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': parent.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Section.objects.filter(pk=parent.pk).exists())

    def test_delete_section_with_empty_children_succeeds(self):
        parent = SectionFactory(project=self.project, title='Parent', number='1', order=0)
        child = SectionFactory(
            project=self.project, title='Child', number='1.1', order=1, parent=parent
        )
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': parent.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Section.objects.filter(pk=parent.pk).exists())
        self.assertFalse(Section.objects.filter(pk=child.pk).exists())

    def test_delete_renumbers_siblings(self):
        s1 = SectionFactory(project=self.project, title='One', number='1', order=0)
        s2 = SectionFactory(project=self.project, title='Two', number='2', order=1)
        s3 = SectionFactory(project=self.project, title='Three', number='3', order=2)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': s2.public_key,
        })
        self.client.post(url)
        s1.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s1.number, '1')
        self.assertEqual(s3.number, '2')

    def test_viewer_cannot_delete_section(self):
        section = SectionFactory(project=self.project, title='Protected', number='1', order=0)
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': section.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_section_from_other_project_returns_404(self):
        other_project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=other_project, user=self.user, role='admin')
        other_section = SectionFactory(project=other_project)
        url = reverse('section_delete', kwargs={
            'slug': self.project.slug, 'public_key': other_section.public_key,
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)


class SectionReorderTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_reorder_sections(self):
        s1 = SectionFactory(project=self.project, title='One', number='1', order=0)
        s2 = SectionFactory(project=self.project, title='Two', number='2', order=1)
        s3 = SectionFactory(project=self.project, title='Three', number='3', order=2)
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [
                {'id': s3.pk, 'parent_id': None},
                {'id': s1.pk, 'parent_id': None},
                {'id': s2.pk, 'parent_id': None},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s3.order, 0)
        self.assertEqual(s1.order, 1)
        self.assertEqual(s2.order, 2)
        self.assertEqual(s3.number, '1')
        self.assertEqual(s1.number, '2')
        self.assertEqual(s2.number, '3')

    def test_reorder_with_nesting(self):
        s1 = SectionFactory(project=self.project, title='One', number='1', order=0)
        s2 = SectionFactory(project=self.project, title='Two', number='2', order=1)
        s3 = SectionFactory(project=self.project, title='Three', number='3', order=2)
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [
                {'id': s1.pk, 'parent_id': None},
                {'id': s2.pk, 'parent_id': s1.pk},
                {'id': s3.pk, 'parent_id': None},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        s2.refresh_from_db()
        self.assertEqual(s2.parent_id, s1.pk)
        self.assertEqual(s2.number, '1.1')
        s3.refresh_from_db()
        self.assertEqual(s3.number, '2')

    def test_reorder_rejects_section_from_other_project(self):
        s1 = SectionFactory(project=self.project, title='One', number='1', order=0)
        other_section = SectionFactory(project=ProjectFactory())
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [
                {'id': s1.pk, 'parent_id': None},
                {'id': other_section.pk, 'parent_id': None},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_reorder_rejects_cycle(self):
        a = SectionFactory(project=self.project, title='A', number='1', order=0)
        b = SectionFactory(project=self.project, title='B', number='2', order=1)
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [
                {'id': a.pk, 'parent_id': b.pk},
                {'id': b.pk, 'parent_id': a.pk},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('circular', response.json()['error'])

    def test_reorder_rejects_deep_cycle(self):
        a = SectionFactory(project=self.project, title='A', number='1', order=0)
        b = SectionFactory(project=self.project, title='B', number='2', order=1)
        c = SectionFactory(project=self.project, title='C', number='3', order=2)
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [
                {'id': a.pk, 'parent_id': c.pk},
                {'id': b.pk, 'parent_id': a.pk},
                {'id': c.pk, 'parent_id': b.pk},
            ],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_reorder(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        url = reverse('section_reorder', kwargs={'slug': self.project.slug})
        response = self.client.post(url, data=json.dumps({
            'order': [],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)


class RenumberSectionsTest(TestCase):

    def test_renumber_flat_sections(self):
        from apps.projects.utils import renumber_sections
        project = ProjectFactory()
        s1 = SectionFactory(project=project, title='A', number='x', order=0)
        s2 = SectionFactory(project=project, title='B', number='y', order=1)
        s3 = SectionFactory(project=project, title='C', number='z', order=2)
        renumber_sections(project)
        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s1.number, '1')
        self.assertEqual(s2.number, '2')
        self.assertEqual(s3.number, '3')

    def test_renumber_nested_sections(self):
        from apps.projects.utils import renumber_sections
        project = ProjectFactory()
        s1 = SectionFactory(project=project, title='A', number='x', order=0)
        s1_1 = SectionFactory(project=project, title='A.1', number='x', order=1, parent=s1)
        s1_2 = SectionFactory(project=project, title='A.2', number='x', order=2, parent=s1)
        s2 = SectionFactory(project=project, title='B', number='x', order=3)
        s2_1 = SectionFactory(project=project, title='B.1', number='x', order=4, parent=s2)
        renumber_sections(project)
        s1.refresh_from_db()
        s1_1.refresh_from_db()
        s1_2.refresh_from_db()
        s2.refresh_from_db()
        s2_1.refresh_from_db()
        self.assertEqual(s1.number, '1')
        self.assertEqual(s1_1.number, '1.1')
        self.assertEqual(s1_2.number, '1.2')
        self.assertEqual(s2.number, '2')
        self.assertEqual(s2_1.number, '2.1')

    def test_renumber_deeply_nested(self):
        from apps.projects.utils import renumber_sections
        project = ProjectFactory()
        s1 = SectionFactory(project=project, title='A', number='x', order=0)
        s1_1 = SectionFactory(project=project, title='A.1', number='x', order=1, parent=s1)
        s1_1_1 = SectionFactory(project=project, title='A.1.1', number='x', order=2, parent=s1_1)
        renumber_sections(project)
        s1.refresh_from_db()
        s1_1.refresh_from_db()
        s1_1_1.refresh_from_db()
        self.assertEqual(s1.number, '1')
        self.assertEqual(s1_1.number, '1.1')
        self.assertEqual(s1_1_1.number, '1.1.1')

    def test_renumber_empty_project(self):
        from apps.projects.utils import renumber_sections
        project = ProjectFactory()
        renumber_sections(project)
