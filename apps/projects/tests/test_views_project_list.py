from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.administration.models import SystemSettings
from apps.doctemplates.factories import TemplateFactory
from apps.projects.factories import (
    OwnedProjectFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
    ItemFactory,
)

PROJECT_LIST_URL = reverse('project_list')


class ProjectListViewAuthTest(TestCase):

    def test_redirects_anonymous(self):
        response = self.client.get(PROJECT_LIST_URL)
        self.assertEqual(response.status_code, 302)


class ProjectListViewScopingTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_shows_owned_projects(self):
        project = OwnedProjectFactory(created_by=self.user, name='My Project')
        response = self.client.get(PROJECT_LIST_URL)
        self.assertContains(response, 'My Project')

    def test_shows_member_projects(self):
        project = ProjectFactory(name='Collab Project')
        ProjectMembershipFactory(project=project, user=self.user)
        response = self.client.get(PROJECT_LIST_URL)
        self.assertContains(response, 'Collab Project')

    def test_hides_other_users_projects(self):
        ProjectFactory(name='Secret Project')
        response = self.client.get(PROJECT_LIST_URL)
        self.assertNotContains(response, 'Secret Project')

    def test_system_admin_sees_all(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        ProjectFactory(name='Any Project')
        response = self.client.get(PROJECT_LIST_URL)
        self.assertContains(response, 'Any Project')


class ProjectListViewStatusFilterTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.active = OwnedProjectFactory(created_by=self.user, status='active', name='Active One')
        self.draft = OwnedProjectFactory(created_by=self.user, status='draft', name='Draft One')
        self.in_review = OwnedProjectFactory(created_by=self.user, status='in-review', name='Review One')
        self.archived = OwnedProjectFactory(created_by=self.user, status='archived', name='Archived One')

    def test_no_filter_shows_all(self):
        response = self.client.get(PROJECT_LIST_URL)
        self.assertEqual(len(response.context['projects']), 4)

    def test_filter_active(self):
        response = self.client.get(PROJECT_LIST_URL, {'status': 'active'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, 'Active One')

    def test_filter_draft(self):
        response = self.client.get(PROJECT_LIST_URL, {'status': 'draft'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, 'Draft One')

    def test_filter_archived(self):
        response = self.client.get(PROJECT_LIST_URL, {'status': 'archived'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, 'Archived One')


class ProjectListViewSearchTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.p1 = OwnedProjectFactory(created_by=self.user, name='Payment Gateway SRS')
        self.p2 = OwnedProjectFactory(created_by=self.user, name='Mobile App Requirements')

    def test_search_by_name(self):
        response = self.client.get(PROJECT_LIST_URL, {'q': 'Payment'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0], self.p1)

    def test_search_case_insensitive(self):
        response = self.client.get(PROJECT_LIST_URL, {'q': 'payment'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 1)

    def test_search_no_results(self):
        response = self.client.get(PROJECT_LIST_URL, {'q': 'Nonexistent'})
        projects = response.context['projects']
        self.assertEqual(len(projects), 0)


class ProjectListViewSortTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_default_sort_by_updated_at(self):
        p1 = OwnedProjectFactory(created_by=self.user, name='AAA')
        p2 = OwnedProjectFactory(created_by=self.user, name='ZZZ')
        response = self.client.get(PROJECT_LIST_URL)
        projects = list(response.context['projects'])
        self.assertEqual(projects[0], p2)

    def test_sort_name_asc(self):
        p_z = OwnedProjectFactory(created_by=self.user, name='Zebra')
        p_a = OwnedProjectFactory(created_by=self.user, name='Alpha')
        response = self.client.get(PROJECT_LIST_URL, {'sort': 'name-asc'})
        projects = list(response.context['projects'])
        self.assertEqual(projects[0], p_a)
        self.assertEqual(projects[1], p_z)

    def test_sort_name_desc(self):
        p_a = OwnedProjectFactory(created_by=self.user, name='Alpha')
        p_z = OwnedProjectFactory(created_by=self.user, name='Zebra')
        response = self.client.get(PROJECT_LIST_URL, {'sort': 'name-desc'})
        projects = list(response.context['projects'])
        self.assertEqual(projects[0], p_z)
        self.assertEqual(projects[1], p_a)

    def test_sort_created(self):
        p1 = OwnedProjectFactory(created_by=self.user, name='First')
        p2 = OwnedProjectFactory(created_by=self.user, name='Second')
        response = self.client.get(PROJECT_LIST_URL, {'sort': 'created'})
        projects = list(response.context['projects'])
        self.assertEqual(projects[0], p2)


class ProjectListViewPaginationTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        tmpl = TemplateFactory()
        for i in range(15):
            OwnedProjectFactory(created_by=self.user, template=tmpl, name=f'Project {i}')

    def test_paginated_to_12(self):
        response = self.client.get(PROJECT_LIST_URL)
        self.assertEqual(len(response.context['projects']), 12)

    def test_page_2_has_remaining(self):
        response = self.client.get(PROJECT_LIST_URL, {'page': 2})
        self.assertEqual(len(response.context['projects']), 3)

    def test_total_count_in_context(self):
        response = self.client.get(PROJECT_LIST_URL)
        self.assertEqual(response.context['total_count'], 15)


class ProjectListViewContextTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_page_carries_no_modal_and_the_create_modal_lists_the_templates(self):
        TemplateFactory(name='Shared Outline', is_builtin=True)
        response = self.client.get(PROJECT_LIST_URL)
        self.assertNotIn('project_form', response.context)
        self.assertNotContains(response, 'id="newProjectModal"')
        self.assertNotContains(response, 'data-bs-toggle="modal"')
        self.assertContains(response, 'data-modal-open="project_create"')
        modal = self.client.get('/modals/project_create/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(modal.status_code, 200)
        self.assertContains(modal, 'Shared Outline')

    def test_status_counts_in_context(self):
        OwnedProjectFactory(created_by=self.user, status='active')
        OwnedProjectFactory(created_by=self.user, status='active')
        OwnedProjectFactory(created_by=self.user, status='draft')
        response = self.client.get(PROJECT_LIST_URL)
        counts = response.context['status_counts']
        self.assertEqual(counts['active'], 2)
        self.assertEqual(counts['draft'], 1)


class ProjectListCountsTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(name='Counted')
        ProjectMembershipFactory(project=self.project, user=self.user, role='editor')
        ProjectMembershipFactory(project=self.project)
        ProjectMembershipFactory(project=self.project)
        section = SectionFactory(project=self.project)
        ItemFactory(project=self.project, section=section, item_id='REQ-001')
        ItemFactory(project=self.project, section=section, item_id='REQ-002')

    def test_counts_cover_the_whole_project_not_the_viewers_membership(self):
        response = self.client.get(PROJECT_LIST_URL)
        project = response.context['projects'][0]
        self.assertEqual((project.items_total, project.members_total), (2, 3))
        self.assertContains(response, '2 items &middot; 3 members')

    def test_queries_do_not_grow_with_the_number_of_projects(self):
        self.client.get(PROJECT_LIST_URL)
        with CaptureQueriesContext(connection) as few:
            self.client.get(PROJECT_LIST_URL)
        for i in range(5):
            extra = ProjectFactory(created_by=self.user, name=f'Extra {i}')
            ProjectMembershipFactory(project=extra, user=self.user, role='admin')
        with CaptureQueriesContext(connection) as many:
            self.client.get(PROJECT_LIST_URL)
        self.assertEqual(len(few), len(many))


class ProjectListViewModeTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        OwnedProjectFactory(created_by=self.user)

    def test_only_the_chosen_view_is_rendered(self):
        grid = self.client.get(PROJECT_LIST_URL)
        self.assertContains(grid, 'id="projectsGrid"')
        self.assertNotContains(grid, 'id="projectsList"')
        table = self.client.get(PROJECT_LIST_URL, {'view': 'table'})
        self.assertContains(table, 'id="projectsList"')
        self.assertNotContains(table, 'id="projectsGrid"')

    def test_the_chosen_view_is_remembered(self):
        response = self.client.get(PROJECT_LIST_URL, {'view': 'table'})
        self.assertEqual(response.cookies['projects_view'].value, 'table')
        self.assertEqual(self.client.get(PROJECT_LIST_URL).context['view_mode'], 'table')
        self.client.get(PROJECT_LIST_URL, {'view': 'grid'})
        self.assertEqual(self.client.get(PROJECT_LIST_URL).context['view_mode'], 'grid')

    def test_unknown_values_fall_back(self):
        response = self.client.get(PROJECT_LIST_URL, {'view': 'x', 'status': 'x', 'sort': 'x'})
        self.assertEqual(response.context['view_mode'], 'grid')
        self.assertEqual(response.context['active_status'], 'all')
        self.assertEqual(response.context['active_sort'], 'updated')
        self.assertNotIn('projects_view', response.cookies)


class ProjectListActionsTest(TestCase):

    def setUp(self):
        self.project = ProjectFactory(name='Acted')

    def page_for(self, user, role=None, **params):
        if role:
            ProjectMembershipFactory(project=self.project, user=user, role=role)
        self.client.force_login(user)
        return self.client.get(PROJECT_LIST_URL, params).content.decode()

    def test_project_admin_gets_every_action_with_confirmations(self):
        html = self.page_for(UserFactory(), 'admin')
        self.assertIn('data-modal-open="project_edit"', html)
        self.assertIn('data-modal-open="project_delete"', html)
        self.assertIn('data-confirm-title="Duplicate Project"', html)
        self.assertIn('data-confirm-title="Archive Project"', html)

    def test_restore_is_confirmed_for_an_archived_project(self):
        self.project.status = 'archived'
        self.project.save()
        html = self.page_for(UserFactory(), 'admin')
        self.assertIn('data-confirm-title="Restore Project"', html)
        self.assertNotIn('data-confirm-title="Duplicate Project"', html)
        self.assertNotIn('data-modal-open="project_edit"', html)

    def test_restore_is_hidden_from_project_admins_while_the_setting_is_off(self):
        stored = SystemSettings.load()
        stored.allow_user_restore = False
        stored.save()
        self.project.status = 'archived'
        self.project.save()
        html = self.page_for(UserFactory(), 'admin')
        self.assertNotIn('data-confirm-title="Restore Project"', html)
        self.assertIn('Only an administrator can restore this project', html)
        self.assertIn('data-modal-open="project_delete"', html)
        html = self.page_for(AdminUserFactory())
        self.assertIn('data-confirm-title="Restore Project"', html)

    def test_editor_can_only_duplicate(self):
        html = self.page_for(UserFactory(), 'editor')
        self.assertIn('data-confirm-title="Duplicate Project"', html)
        self.assertNotIn('data-modal-open="project_edit"', html)
        self.assertNotIn('data-modal-open="project_delete"', html)
        self.assertNotIn('data-confirm-title="Archive Project"', html)

    def test_project_viewer_gets_no_actions_menu(self):
        html = self.page_for(UserFactory(), 'viewer')
        self.assertNotIn('class="project-actions"', html)

    def test_system_viewer_cannot_duplicate_or_create(self):
        html = self.page_for(ViewerUserFactory(), 'editor')
        self.assertNotIn('data-confirm-title="Duplicate Project"', html)
        self.assertNotIn('data-modal-open="project_create"', html)

    def test_system_admin_gets_every_action(self):
        html = self.page_for(AdminUserFactory())
        self.assertIn('data-modal-open="project_delete"', html)

    def test_the_table_carries_the_same_actions(self):
        html = self.page_for(UserFactory(), 'admin', view='table')
        self.assertIn('data-confirm-title="Duplicate Project"', html)
        self.assertIn('data-modal-open="project_delete"', html)


class ProjectListEmptyStatesTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_no_projects_offers_to_create_one(self):
        response = self.client.get(PROJECT_LIST_URL)
        self.assertContains(response, 'No projects yet')
        self.assertContains(response, 'data-modal-open="project_create"')

    def test_no_match_offers_to_clear_the_filters(self):
        OwnedProjectFactory(created_by=self.user, name='Alpha')
        response = self.client.get(PROJECT_LIST_URL, {'q': 'zzz', 'status': 'draft', 'sort': 'name-asc'})
        self.assertContains(response, 'No projects match')
        self.assertContains(response, 'Clear filters')
        self.assertContains(response, 'href="?sort=name-asc"')
        self.assertNotContains(response, 'No projects yet')


class ProjectListPaginationLinksTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        for i in range(14):
            OwnedProjectFactory(created_by=self.user, name=f'Active {i}', status='active')
        OwnedProjectFactory(created_by=self.user, name='Draft one', status='draft')

    def test_page_links_keep_the_filters(self):
        response = self.client.get(PROJECT_LIST_URL, {'status': 'active', 'q': 'Active'})
        self.assertContains(response, 'href="?status=active&amp;q=Active&amp;page=2"')
        self.assertContains(response, 'Showing 1-12 of 14')

    def test_status_links_reset_the_page(self):
        response = self.client.get(PROJECT_LIST_URL, {'status': 'active', 'page': 2})
        self.assertContains(response, 'href="?status=draft"')
