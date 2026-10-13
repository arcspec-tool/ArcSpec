import re

from allauth.socialaccount.models import SocialAccount
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.models import UserSettings
from apps.administration.models import SystemSettings
from apps.projects.models import Project
from apps.notifications.factories import AuditLogFactory
from apps.notifications.models import AuditLog
from apps.projects.factories import (
    CommentFactory,
    ItemFactory,
    ProjectFactory,
    ProjectMembershipFactory,
    SectionFactory,
)


class LoginViewTest(TestCase):

    def test_authenticated_user_redirects_to_dashboard(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertRedirects(response, '/dashboard/')


class LogoutViewTest(TestCase):

    def test_get_is_refused_and_keeps_the_session(self):
        self.client.force_login(UserFactory())
        response = self.client.get('/logout/')
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_signs_out_and_redirects_to_login(self):
        self.client.force_login(UserFactory())
        response = self.client.post('/logout/')
        self.assertRedirects(response, '/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_post_without_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(UserFactory())
        response = client.post('/logout/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('_auth_user_id', client.session)

    def test_signed_in_pages_open_the_sign_out_modal_from_two_triggers(self):
        self.client.force_login(UserFactory())
        response = self.client.get('/profile/')
        self.assertNotContains(response, 'action="/logout/"')
        self.assertContains(response, 'data-modal-open="sign_out"', count=2)
        self.assertNotContains(response, 'account_logout')
        modal = self.client.get('/modals/sign_out/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        forms_with_token = re.findall(
            r'<form method="post" action="/logout/">\s*<input type="hidden" name="csrfmiddlewaretoken"',
            modal.content.decode(),
        )
        self.assertEqual(len(forms_with_token), 1)


class ProfileViewTest(TestCase):

    def test_unauthenticated_redirects(self):
        response = self.client.get('/profile/')
        self.assertRedirects(response, '/?next=/profile/')

    def test_context_has_assigned_projects(self):
        user = UserFactory()
        p1 = ProjectFactory(created_by=user)
        ProjectMembershipFactory(project=p1, user=user, role='admin')
        p2 = ProjectFactory()
        ProjectMembershipFactory(project=p2, user=user, role='editor')
        ProjectFactory()
        self.client.force_login(user)
        response = self.client.get('/profile/')
        projects = response.context['assigned_projects']
        self.assertEqual(len(projects), 2)
        project_pks = [p.pk for p in projects]
        self.assertIn(p1.pk, project_pks)
        self.assertIn(p2.pk, project_pks)

    def test_assigned_projects_include_role(self):
        user = UserFactory()
        project = ProjectFactory()
        ProjectMembershipFactory(project=project, user=user, role='editor')
        self.client.force_login(user)
        response = self.client.get('/profile/')
        projects = response.context['assigned_projects']
        self.assertEqual(projects[0].user_role, 'editor')

    def test_context_has_activity_stats(self):
        user = UserFactory()
        project = ProjectFactory(created_by=user)
        ProjectMembershipFactory(project=project, user=user, role='admin')
        section = SectionFactory(project=project)
        item = ItemFactory(project=project, section=section, created_by=user)
        CommentFactory(item=item, author=user)
        CommentFactory(item=item, author=user)
        self.client.force_login(user)
        response = self.client.get('/profile/')
        stats = response.context['activity_stats']
        self.assertEqual(stats['projects_count'], 1)
        self.assertEqual(stats['items_created'], 1)
        self.assertEqual(stats['comments_count'], 2)

    def test_recent_activity_shows_six_rows_and_offers_load_more(self):
        user = UserFactory()
        project = ProjectFactory(created_by=user)
        ProjectMembershipFactory(project=project, user=user, role='admin')
        for i in range(15):
            AuditLogFactory(project=project, user=user, action='created', target_type='Item', target_id=f'REQ-{i:03d}')
        self.client.force_login(user)
        response = self.client.get('/profile/')
        activity = response.context['recent_activity']
        self.assertEqual(len(activity), 6)
        self.assertTrue(response.context['activity_has_more'])
        self.assertContains(response, 'id="loadMoreActivity"')
        self.assertContains(response, 'data-url="/profile/activity/"')
        self.assertContains(response, 'data-list="activityFeedList"')
        self.assertContains(response, 'data-offset="6"')

    def test_page_has_no_profile_modal_and_the_modal_is_prefilled(self):
        user = UserFactory(first_name='Prefilled', last_name='Person')
        self.client.force_login(user)
        response = self.client.get('/profile/')
        self.assertNotIn('edit_profile_form', response.context)
        self.assertNotContains(response, 'id="editProfileModal"')
        self.assertContains(response, 'data-modal-open="edit_profile"')
        modal = self.client.get('/modals/edit_profile/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(modal.status_code, 200)
        self.assertContains(modal, 'value="Prefilled"')
        self.assertContains(modal, 'data-modal-form')

    def test_invalid_profile_post_from_the_modal_returns_the_bound_modal(self):
        user = UserFactory(first_name='Keep', last_name='Me')
        self.client.force_login(user)
        response = self.client.post('/profile/', {
            'first_name': '',
            'last_name': 'Me',
            'display_name': 'Typed display',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 422)
        html = response.content.decode()
        self.assertIn('data-modal-name="edit_profile"', html)
        self.assertIn('is-invalid', html)
        self.assertIn('This field is required.', html)
        self.assertIn('value="Typed display"', html)
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Keep')

    def test_invalid_profile_post_without_the_header_redirects_with_a_message(self):
        user = UserFactory(first_name='Keep', last_name='Me')
        self.client.force_login(user)
        response = self.client.post('/profile/', {'first_name': '', 'last_name': 'Me'})
        self.assertRedirects(response, '/profile/', fetch_redirect_response=False)
        self.assertContains(self.client.get('/profile/'), 'Please correct the errors below.')

    def test_edit_profile_post(self):
        user = UserFactory(first_name='Old', last_name='Name')
        self.client.force_login(user)
        response = self.client.post('/profile/', {
            'first_name': 'New',
            'last_name': 'Person',
            'display_name': 'New P.',
            'department': 'Engineering',
            'location': 'Vilnius',
            'phone': '+370 600 12345',
        })
        self.assertRedirects(response, '/profile/')
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'New')
        self.assertEqual(user.last_name, 'Person')
        self.assertEqual(user.display_name, 'New P.')
        self.assertEqual(user.department, 'Engineering')


class ProfilePageTest(TestCase):

    def setUp(self):
        self.user = UserFactory(first_name='Ada', last_name='Lovelace', display_name='', department='', location='', phone='')
        self.client.force_login(self.user)

    def test_projects_most_recent_first_archived_last_with_counts(self):
        older = ProjectFactory(name='Older')
        newer = ProjectFactory(name='Newer')
        archived = ProjectFactory(name='Shelved', status='archived')
        for project, role in ((older, 'admin'), (newer, 'editor'), (archived, 'viewer')):
            ProjectMembershipFactory(project=project, user=self.user, role=role)
        Project.objects.filter(pk=older.pk).update(updated_at=timezone.now() - timezone.timedelta(days=3))
        section = SectionFactory(project=newer)
        ItemFactory(project=newer, section=section, item_id='REQ-001')
        response = self.client.get('/profile/')
        names = [p.name for p in response.context['assigned_projects']]
        self.assertEqual(names, ['Newer', 'Older', 'Shelved'])
        self.assertContains(response, 'Editor &middot; 1 item &middot;')

    def test_queries_do_not_grow_with_the_number_of_projects(self):
        ProjectMembershipFactory(project=ProjectFactory(), user=self.user)
        self.client.get('/profile/')
        with CaptureQueriesContext(connection) as few:
            self.client.get('/profile/')
        for _ in range(4):
            ProjectMembershipFactory(project=ProjectFactory(), user=self.user)
        with CaptureQueriesContext(connection) as many:
            self.client.get('/profile/')
        self.assertEqual(len(few), len(many))

    def test_activity_rows_link_to_their_project_without_the_actor(self):
        project = ProjectFactory()
        ProjectMembershipFactory(project=project, user=self.user)
        AuditLogFactory(project=project, user=self.user, action='created', target_type='Item', target_id='REQ-007')
        html = self.client.get('/profile/').content.decode()
        self.assertIn(f'<a href="{project.get_absolute_url()}" class="dash-row dash-activity">', html)
        self.assertIn('<span class="dash-row-title">Created item <span class="dash-target">REQ-007</span>', html)
        self.assertNotIn('class="dash-actor"', html)

    def test_password_sign_in_offers_change_password_when_enabled(self):
        self.user.set_password('a-long-throwaway-password')
        self.user.save()
        self.client.force_login(self.user)
        stored = SystemSettings.load()
        stored.password_login_enabled = True
        stored.save()
        self.assertContains(self.client.get('/profile/'), 'Change password')
        stored.password_login_enabled = False
        stored.save()
        self.assertNotContains(self.client.get('/profile/'), 'Change password')

    def test_microsoft_sign_in_is_named(self):
        SocialAccount.objects.create(user=self.user, provider='microsoft', uid='ms-uid-1')
        self.assertContains(self.client.get('/profile/'), 'Microsoft account')


class ProfileNamesManagedTest(TestCase):

    def setUp(self):
        self.user = UserFactory(first_name='Given', last_name='Family', display_name='')
        SocialAccount.objects.create(user=self.user, provider='microsoft', uid='ms-uid-2')
        self.client.force_login(self.user)

    def test_names_are_read_only_and_explained_in_the_modal(self):
        modal = self.client.get('/modals/edit_profile/', HTTP_X_REQUESTED_WITH='XMLHttpRequest').content.decode()
        self.assertIn('id="namesManagedHelp"', modal)
        self.assertRegex(modal, r'id="id_first_name" autocomplete="given-name" disabled')

    def test_posted_names_are_ignored_and_other_fields_saved(self):
        response = self.client.post('/profile/', {'first_name': 'Typed', 'last_name': '', 'display_name': 'Chosen', 'department': 'Ops'})
        self.assertRedirects(response, '/profile/')
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name, self.user.display_name, self.user.department), ('Given', 'Family', 'Chosen', 'Ops'))

    def test_a_linked_account_without_names_can_type_them(self):
        bare = UserFactory(first_name='', last_name='')
        SocialAccount.objects.create(user=bare, provider='microsoft', uid='ms-uid-3')
        self.client.force_login(bare)
        modal = self.client.get('/modals/edit_profile/', HTTP_X_REQUESTED_WITH='XMLHttpRequest').content.decode()
        self.assertIn('Optional. If your Microsoft account provides your name', modal)
        self.assertNotIn(' disabled', modal)
        self.client.post('/profile/', {'first_name': 'New', 'last_name': 'Name'})
        bare.refresh_from_db()
        self.assertEqual((bare.first_name, bare.last_name), ('New', 'Name'))

    def test_a_linked_account_without_names_saves_other_fields(self):
        bare = UserFactory(first_name='', last_name='', display_name='Shown')
        SocialAccount.objects.create(user=bare, provider='microsoft', uid='ms-uid-4')
        self.client.force_login(bare)
        response = self.client.post('/profile/', {'first_name': '', 'last_name': '', 'display_name': 'Shown', 'department': 'Ops'})
        self.assertRedirects(response, '/profile/')
        bare.refresh_from_db()
        self.assertEqual(bare.department, 'Ops')


class SettingsViewTest(TestCase):

    def test_unauthenticated_redirects(self):
        response = self.client.get('/settings/')
        self.assertRedirects(response, '/?next=/settings/')

    def test_every_section_is_on_one_page(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get('/settings/')
        for section in ('notifications', 'export', 'account'):
            self.assertContains(response, f'id="{section}"')
        self.assertEqual(response.content.decode().count('<form method="post" action="/settings/" data-settings-form>'), 2)

    def test_notification_form_populated_with_current_settings(self):
        user = UserFactory()
        settings = user.settings
        settings.notify_project_updates = False
        settings.save()
        self.client.force_login(user)
        response = self.client.get('/settings/')
        form = response.context['notification_form']
        self.assertFalse(form.initial['notify_project_updates'])

    def test_save_notification_settings(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post('/settings/', {
            'form_type': 'notifications',
            'notify_project_updates': True,
            'notify_comments': True,
            'notify_status_changes': False,
            'notify_collaborator_changes': False,
            'notify_weekly_digest': True,
        })
        self.assertRedirects(response, '/settings/#notifications', fetch_redirect_response=False)
        user.settings.refresh_from_db()
        self.assertFalse(user.settings.notify_status_changes)
        self.assertTrue(user.settings.notify_weekly_digest)

    def test_save_export_defaults(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post('/settings/', {
            'form_type': 'export',
            'export_paper_size': 'letter',
            'export_orientation': 'landscape',
            'export_include_toc': True,
            'export_include_attributes': False,
            'export_include_comments': True,
            'export_include_links': False,
        })
        self.assertRedirects(response, '/settings/#export', fetch_redirect_response=False)
        user.settings.refresh_from_db()
        self.assertEqual(user.settings.export_paper_size, 'letter')
        self.assertEqual(user.settings.export_orientation, 'landscape')
        self.assertTrue(user.settings.export_include_comments)
        self.assertFalse(user.settings.export_include_attributes)


class SettingsSaveAsYouChangeTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)

    def test_a_section_saves_over_ajax_and_answers_json(self):
        response = self.client.post('/settings/', {
            'form_type': 'notifications',
            'notify_comments': 'on',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'message': 'Email notification settings saved.'})
        self.user.settings.refresh_from_db()
        self.assertTrue(self.user.settings.notify_comments)
        self.assertFalse(self.user.settings.notify_project_updates)

    def test_an_invalid_value_answers_400_and_saves_nothing(self):
        response = self.client.post('/settings/', {
            'form_type': 'export', 'export_paper_size': 'a0', 'export_orientation': 'portrait',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertIn('export_paper_size', response.json()['errors'])
        self.user.settings.refresh_from_db()
        self.assertEqual(self.user.settings.export_paper_size, 'a4')

    def test_an_unknown_section_answers_400(self):
        response = self.client.post('/settings/', {'form_type': 'bogus'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)

    SWITCHES = {
        'notifications': ('notify_project_updates', 'notify_comments', 'notify_status_changes', 'notify_collaborator_changes', 'notify_weekly_digest'),
        'export': ('export_include_toc', 'export_include_attributes', 'export_include_comments', 'export_include_links'),
    }
    SELECTS = {'export_paper_size': 'a4', 'export_orientation': 'portrait'}

    def save(self, form_type, **data):
        return self.client.post('/settings/', {'form_type': form_type, **data}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def stored(self):
        self.user.settings.refresh_from_db()
        return self.user.settings

    def test_every_switch_saves_on_and_off_without_touching_the_others(self):
        for form_type, fields in self.SWITCHES.items():
            base = dict(self.SELECTS) if form_type == 'export' else {}
            for field in fields:
                others = {other: 'on' for other in fields if other != field}
                self.assertEqual(self.save(form_type, **base, **others, **{field: 'on'}).status_code, 200, field)
                self.assertTrue(getattr(self.stored(), field), field)
                self.assertEqual(self.save(form_type, **base, **others).status_code, 200, field)
                stored = self.stored()
                self.assertFalse(getattr(stored, field), field)
                for other in others:
                    self.assertTrue(getattr(stored, other), (field, other))

    def test_every_paper_size_and_orientation_saves(self):
        from apps.accounts.models import UserSettings
        for paper, _ in UserSettings.PAPER_SIZE_CHOICES:
            for orientation, _ in UserSettings.ORIENTATION_CHOICES:
                response = self.save('export', export_paper_size=paper, export_orientation=orientation)
                self.assertEqual(response.status_code, 200, (paper, orientation))
                stored = self.stored()
                self.assertEqual((stored.export_paper_size, stored.export_orientation), (paper, orientation))
        response = self.save('export', export_paper_size='a4', export_orientation='sideways')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.json()['errors']), ['export_orientation'])
        self.assertEqual(self.stored().export_orientation, 'landscape')

    def test_every_saved_field_has_its_control_on_the_page_and_nothing_else_is_offered(self):
        from apps.accounts.forms import ExportDefaultsForm, NotificationSettingsForm
        html = self.client.get('/settings/').content.decode()
        offered = set(re.findall(r'name="((?:notify_|export_)\w+)"', html))
        self.assertEqual(offered, set(NotificationSettingsForm.Meta.fields) | set(ExportDefaultsForm.Meta.fields))
        self.assertEqual(html.count('name="form_type" value="notifications"'), 1)
        self.assertEqual(html.count('name="form_type" value="export"'), 1)
        for field in offered:
            self.assertIn(f'for="id_{field}"', html, field)

    def test_no_dead_export_options_are_offered(self):
        html = self.client.get('/settings/').content.decode()
        self.assertNotIn('export_format', html)
        self.assertNotIn('export_include_history', html)

    def test_the_export_dialog_preselects_the_saved_defaults(self):
        project = ProjectFactory()
        ProjectMembershipFactory(project=project, user=self.user, role='viewer')
        stored = self.user.settings
        stored.export_paper_size = 'letter'
        stored.export_orientation = 'landscape'
        stored.export_include_toc = False
        stored.export_include_comments = True
        stored.save()
        html = self.client.get(f'/modals/export/?project={project.slug}', HTTP_X_REQUESTED_WITH='XMLHttpRequest').content.decode()
        self.assertIn('<option value="letter" selected>', html)
        self.assertIn('<option value="landscape" selected>', html)
        self.assertRegex(html, r'name="include_toc" id="exportToc">')
        self.assertRegex(html, r'name="include_comments" id="exportComments" checked>')
        self.assertNotIn('include_history', html)


class ProfileLoadMoreActivityTest(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.client.force_login(self.user)
        self.project = ProjectFactory(created_by=self.user)
        ProjectMembershipFactory(project=self.project, user=self.user, role='admin')
        AuditLog.objects.all().delete()

    def make_rows(self, count, start=0):
        return [
            AuditLogFactory(project=self.project, user=self.user, action='created', target_type='Item', target_id=f'REQ-{i:03}')
            for i in range(start, start + count)
        ]

    def load(self, **params):
        return self.client.get('/profile/activity/', params, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_button_shown_only_when_more_than_six_exist(self):
        self.make_rows(6)
        self.assertNotContains(self.client.get('/profile/'), 'id="loadMoreActivity"')
        self.make_rows(1, start=6)
        self.assertContains(self.client.get('/profile/'), 'id="loadMoreActivity"')

    def test_load_more_continues_after_the_first_page_without_the_actor(self):
        self.make_rows(15)
        page = self.client.get('/profile/').context
        first = [a.target_id for a in page['recent_activity']]
        response = self.load(offset=6, until=page['activity_until'])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['has_more'])
        self.assertEqual(data['html'].count('class="dash-row dash-activity"'), 9)
        self.assertNotIn('dash-actor', data['html'])
        loaded = [f'REQ-{i:03}' for i in range(15) if f'<span class="dash-target">REQ-{i:03}</span>' in data['html']]
        self.assertEqual(sorted(first + loaded), [f'REQ-{i:03}' for i in range(15)])

    def test_rows_created_after_the_page_are_not_loaded(self):
        self.make_rows(8)
        until = self.client.get('/profile/').context['activity_until']
        self.make_rows(3, start=8)
        data = self.load(offset=6, until=until).json()
        self.assertEqual(data['html'].count('class="dash-row dash-activity"'), 2)
        self.assertNotIn('<span class="dash-target">REQ-010</span>', data['html'])

    def test_only_the_users_own_rows_in_their_projects(self):
        other = UserFactory()
        ProjectMembershipFactory(project=self.project, user=other, role='editor')
        AuditLog.objects.all().delete()
        AuditLogFactory(project=self.project, user=other, action='created', target_type='Item', target_id='THEIRS-1')
        AuditLogFactory(project=ProjectFactory(), user=self.user, action='created', target_type='Item', target_id='ELSEWHERE-1')
        self.make_rows(1)
        html = self.load(offset=0).json()['html']
        self.assertNotIn('THEIRS-1', html)
        self.assertNotIn('ELSEWHERE-1', html)
        self.assertEqual(html.count('class="dash-row dash-activity"'), 1)

    def test_invalid_parameters_return_400(self):
        for params in ({'offset': 'abc'}, {'offset': -1}, {'offset': 5, 'until': 'nope'}, {'offset': 5, 'until': '2026-10-10T10:00:00'}):
            self.assertEqual(self.load(**params).status_code, 400, params)

    def test_anonymous_sent_to_sign_in(self):
        self.client.logout()
        response = self.load(offset=5)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response['X-Redirect-To'].startswith('/?next='))
