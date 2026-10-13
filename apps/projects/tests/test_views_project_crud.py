from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.administration.models import SystemSettings
from apps.doctemplates.factories import TemplateFactory
from apps.notifications.models import Notification
from apps.projects.factories import (
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    ItemFactory,
)
from apps.projects.models import Project


class ProjectCreateTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.template = TemplateFactory(created_by=self.user)

    def test_create_project_refuses_another_users_private_template(self):
        private = TemplateFactory()
        response = self.client.post(reverse('project_create'), {
            'name': 'Leak',
            'template': private.pk,
            'status': 'draft',
            'color': '#284E8A',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Project.objects.filter(name='Leak').exists())

    def test_create_project_accepts_builtin_global_and_own_templates(self):
        for template in (TemplateFactory(is_builtin=True), TemplateFactory(is_global=True), self.template):
            response = self.client.post(reverse('project_create'), {
                'name': f'From {template.name}',
                'template': template.pk,
                'status': 'draft',
                'color': '#284E8A',
            })
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Project.objects.filter(name=f'From {template.name}', template=template).exists())

    def test_the_new_project_form_offers_only_visible_templates(self):
        TemplateFactory(name='Private of someone else')
        TemplateFactory(name='Shared with everyone', is_global=True)
        url = reverse('modal', args=['project_create'])
        response = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertContains(response, 'Shared with everyone')
        self.assertContains(response, self.template.name)
        self.assertNotContains(response, 'Private of someone else')
        self.client.force_login(AdminUserFactory())
        self.assertContains(self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest'), 'Private of someone else')

    def test_create_project(self):
        response = self.client.post(reverse('project_create'), {
            'name': 'New Project',
            'description': 'A test project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(name='New Project')
        self.assertEqual(project.created_by, self.user)
        self.assertEqual(project.template, self.template)
        self.assertEqual(project.color, '#284E8A')

    def test_creating_a_project_sends_its_creator_no_notification(self):
        self.client.post(reverse('project_create'), {
            'name': 'Quiet Project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertTrue(Project.objects.filter(name='Quiet Project').exists())
        self.assertFalse(Notification.objects.filter(user=self.user).exists())

    def test_create_project_auto_slug(self):
        self.client.post(reverse('project_create'), {
            'name': 'My Cool Project',
            'template': self.template.pk,
            'status': 'draft',
            'color': '#284E8A',
        })
        project = Project.objects.get(name='My Cool Project')
        self.assertEqual(project.slug, 'my-cool-project')

    def test_create_project_creates_sections_from_template(self):
        from apps.doctemplates.models import TemplateSection
        TemplateSection.objects.create(
            template=self.template, title='Introduction', number='1', order=0
        )
        TemplateSection.objects.create(
            template=self.template, title='Scope', number='2', order=1
        )
        self.client.post(reverse('project_create'), {
            'name': 'Sectioned Project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        project = Project.objects.get(name='Sectioned Project')
        self.assertEqual(project.sections.count(), 2)

    def test_create_project_copies_section_descriptions_from_template(self):
        from apps.doctemplates.models import TemplateSection
        TemplateSection.objects.create(
            template=self.template, title='Introduction', number='1', order=0,
            description='Overview of the document',
        )
        self.client.post(reverse('project_create'), {
            'name': 'With Descriptions',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        project = Project.objects.get(name='With Descriptions')
        section = project.sections.get(title='Introduction')
        self.assertEqual(section.description, 'Overview of the document')

    def test_create_project_adds_owner_as_admin_member(self):
        self.client.post(reverse('project_create'), {
            'name': 'Owned Project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        project = Project.objects.get(name='Owned Project')
        membership = project.memberships.get(user=self.user)
        self.assertEqual(membership.role, 'admin')

    def test_create_requires_name(self):
        response = self.client.post(reverse('project_create'), {
            'name': '',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertEqual(Project.objects.count(), 0)

    def test_create_requires_template(self):
        response = self.client.post(reverse('project_create'), {
            'name': 'No Template',
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertEqual(Project.objects.count(), 0)

    def test_create_anonymous_redirects(self):
        self.client.logout()
        response = self.client.post(reverse('project_create'), {
            'name': 'Anon',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), 0)

    def test_duplicate_slug_appends_suffix(self):
        ProjectFactory(name='My Project', slug='my-project')
        self.client.post(reverse('project_create'), {
            'name': 'My Project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        project = Project.objects.filter(name='My Project').exclude(slug='my-project').first()
        self.assertIsNotNone(project)
        self.assertTrue(project.slug.startswith('my-project'))
        self.assertNotEqual(project.slug, 'my-project')

    def test_viewer_cannot_create_project(self):
        viewer = UserFactory(system_role='viewer')
        self.client.force_login(viewer)
        response = self.client.post(reverse('project_create'), {
            'name': 'Viewer Project',
            'template': self.template.pk,
            'status': 'active',
            'color': '#284E8A',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Project.objects.count(), 0)


class ProjectUpdateTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user, name='Original')
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_update_project_name(self):
        response = self.client.post(
            reverse('project_update', kwargs={'slug': self.project.slug}),
            {
                'name': 'Updated Name',
                'description': self.project.description,
                'status': self.project.status,
                'color': self.project.color,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Updated Name')

    def test_update_project_color(self):
        self.client.post(
            reverse('project_update', kwargs={'slug': self.project.slug}),
            {
                'name': self.project.name,
                'description': '',
                'status': 'active',
                'color': '#dc3545',
            }
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.color, '#dc3545')

    def test_setting_status_archived_in_edit_records_the_archive_date(self):
        before = timezone.now()
        self.client.post(
            reverse('project_update', kwargs={'slug': self.project.slug}),
            {'name': self.project.name, 'description': '', 'status': 'archived', 'color': self.project.color}
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'archived')
        self.assertTrue(before <= self.project.archived_at <= timezone.now())

    def test_non_admin_cannot_update(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        response = self.client.post(
            reverse('project_update', kwargs={'slug': self.project.slug}),
            {'name': 'Hacked', 'status': 'active', 'color': '#000'}
        )
        self.assertEqual(response.status_code, 403)

    def test_non_member_gets_404(self):
        stranger = UserFactory()
        self.client.force_login(stranger)
        response = self.client.post(
            reverse('project_update', kwargs={'slug': self.project.slug}),
            {'name': 'Hacked', 'status': 'active', 'color': '#000'}
        )
        self.assertEqual(response.status_code, 404)


class ProjectArchiveRestoreTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user, status='active')
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_archive_project(self):
        response = self.client.post(
            reverse('project_archive', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'archived')
        self.assertIsNotNone(self.project.archived_at)

    def test_restore_project(self):
        self.project.status = 'archived'
        self.project.save()
        response = self.client.post(
            reverse('project_restore', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'active')
        self.assertIsNone(self.project.archived_at)

    def test_non_admin_cannot_archive(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        response = self.client.post(
            reverse('project_archive', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 403)

    def test_restore_follows_the_user_restore_setting(self):
        stored = SystemSettings.load()
        stored.allow_user_restore = False
        stored.save()
        self.project.status = 'archived'
        self.project.save()
        response = self.client.post(reverse('project_restore', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'archived')
        self.client.force_login(AdminUserFactory())
        response = self.client.post(reverse('project_restore', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'active')


class ProjectDeleteTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')

    def test_delete_project(self):
        slug = self.project.slug
        response = self.client.post(
            reverse('project_delete', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Project.objects.filter(slug=slug).exists())

    def test_non_admin_cannot_delete(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        response = self.client.post(
            reverse('project_delete', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_non_member_gets_404(self):
        stranger = UserFactory()
        self.client.force_login(stranger)
        response = self.client.post(
            reverse('project_delete', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 404)


class ProjectDuplicateTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user, name='Original Project')
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')
        self.section = SectionFactory(project=self.project, title='Intro', number='1')

    def test_duplicate_project(self):
        response = self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 302)
        copy = Project.objects.filter(name='Original Project (Copy)').first()
        self.assertIsNotNone(copy)
        self.assertEqual(copy.created_by, self.user)
        self.assertEqual(copy.template, self.project.template)

    def test_duplicate_copies_sections(self):
        self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        copy = Project.objects.get(name='Original Project (Copy)')
        self.assertEqual(copy.sections.count(), 1)
        self.assertEqual(copy.sections.first().title, 'Intro')

    def test_duplicate_copies_section_descriptions(self):
        self.section.description = 'Intro description'
        self.section.save()
        self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        copy = Project.objects.get(name='Original Project (Copy)')
        copied_section = copy.sections.get(title='Intro')
        self.assertEqual(copied_section.description, 'Intro description')

    def test_duplicate_does_not_copy_items(self):
        ItemFactory(project=self.project, section=self.section, item_id='REQ-001')
        self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        copy = Project.objects.get(name='Original Project (Copy)')
        self.assertEqual(copy.items.count(), 0)

    def test_duplicate_resets_next_item_number(self):
        self.project.next_item_number = 42
        self.project.save()
        self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        copy = Project.objects.get(name='Original Project (Copy)')
        self.assertEqual(copy.next_item_number, 1)

    def test_an_editor_can_duplicate(self):
        editor = UserFactory()
        ProjectMembershipFactory(project=self.project, user=editor, role='editor')
        self.client.force_login(editor)
        response = self.client.post(reverse('project_duplicate', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.get(name='Original Project (Copy)').created_by, editor)

    def test_a_project_viewer_cannot_duplicate(self):
        viewer = UserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='viewer')
        self.client.force_login(viewer)
        response = self.client.post(reverse('project_duplicate', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(name='Original Project (Copy)').exists())

    def test_a_system_viewer_cannot_duplicate_even_as_an_editor(self):
        viewer = ViewerUserFactory()
        ProjectMembershipFactory(project=self.project, user=viewer, role='editor')
        self.client.force_login(viewer)
        response = self.client.post(reverse('project_duplicate', kwargs={'slug': self.project.slug}))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(name='Original Project (Copy)').exists())

    def test_non_member_cannot_duplicate(self):
        stranger = UserFactory()
        self.client.force_login(stranger)
        response = self.client.post(
            reverse('project_duplicate', kwargs={'slug': self.project.slug})
        )
        self.assertEqual(response.status_code, 404)
