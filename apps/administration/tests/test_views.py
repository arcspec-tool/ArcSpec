from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.factories import AdminUserFactory, UserFactory, ViewerUserFactory
from apps.accounts.models import User
from apps.accounts.tests.test_auth_methods import ENTRA_UNCONFIGURED, messages_of, set_methods
from apps.accounts.tests.test_callback_prefix import ENTRA_CONFIGURED
from apps.administration.models import SystemSettings
from apps.doctemplates.factories import TemplateFactory
from apps.projects.factories import ItemFactory, ItemTagFactory, PresetTagFactory, ProjectFactory
from apps.projects.models import Tag


class AdminPanelViewTest(TestCase):

    def test_unauthenticated_redirects(self):
        response = self.client.get('/admin-panel/')
        self.assertRedirects(response, '/?next=/admin-panel/')

    def test_non_admin_gets_403(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get('/admin-panel/')
        self.assertEqual(response.status_code, 403)

    def test_viewer_gets_403(self):
        viewer = ViewerUserFactory()
        self.client.force_login(viewer)
        response = self.client.get('/admin-panel/')
        self.assertEqual(response.status_code, 403)

    def test_active_tab_from_query_param(self):
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get('/admin-panel/?tab=tags')
        self.assertEqual(response.context['active_tab'], 'tags')

    def test_an_unknown_tab_falls_back_to_users(self):
        self.client.force_login(AdminUserFactory())
        response = self.client.get('/admin-panel/?tab=nope')
        self.assertEqual(response.context['active_tab'], 'users')

    def test_the_tabs_are_links_and_only_the_active_tab_is_rendered(self):
        self.client.force_login(AdminUserFactory())
        html = self.client.get('/admin-panel/?tab=users').content.decode()
        self.assertIn('href="?tab=templates"', html)
        self.assertIn('href="?tab=system"', html)
        self.assertNotIn('data-bs-toggle="tab"', html)
        self.assertIn('data-modal-open="invite_user"', html)
        self.assertNotIn('data-modal-open="tag_preset"', html)
        self.assertNotIn('value="authentication"', html)
        html = self.client.get('/admin-panel/?tab=system').content.decode()
        self.assertIn('value="authentication"', html)
        self.assertNotIn('data-modal-open="invite_user"', html)


class AdminUsersTabTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory(first_name='Site', last_name='Admin')
        self.client.force_login(self.admin)

    def page(self, **params):
        return self.client.get('/admin-panel/', {'tab': 'users', **params})

    def test_the_display_name_is_shown_and_searched(self):
        user = UserFactory(first_name='Ann', last_name='Lee', display_name='Annie L', email='ann@example.com')
        html = self.page().content.decode()
        self.assertIn('Annie L', html)
        self.assertIn('ann@example.com', html)
        response = self.page(user_q='Annie')
        self.assertEqual([u.pk for u in response.context['user_list']], [user.pk])
        response = self.page(user_q='nobody-here')
        self.assertEqual(list(response.context['user_list']), [])
        self.assertContains(response, 'No users match')
        self.assertContains(response, 'href="?tab=users"')

    def test_the_role_filter_narrows_the_list_and_counts_every_role(self):
        viewer = ViewerUserFactory()
        UserFactory()
        response = self.page(role='viewer')
        self.assertEqual([u.pk for u in response.context['user_list']], [viewer.pk])
        self.assertEqual(response.context['role_filter'], 'viewer')
        self.assertEqual(
            response.context['role_filters'],
            [('', 'All', 3), ('admin', 'Administrator', 1), ('user', 'User', 1), ('viewer', 'Viewer', 1)],
        )
        self.assertContains(response, 'href="?tab=users&amp;role=viewer" class="segmented-link active"')
        self.assertContains(response, '<input type="hidden" name="role" value="viewer">')
        response = self.page(role='emperor')
        self.assertEqual(response.context['role_filter'], '')
        self.assertEqual(len(response.context['user_list']), 3)

    def test_the_search_form_keeps_the_tab_and_the_role(self):
        html = self.page(role='user').content.decode()
        self.assertIn('<input type="hidden" name="tab" value="users">', html)
        self.assertIn('<input type="hidden" name="role" value="user">', html)
        self.assertIn('id="adminUserSearch"', html)

    def test_the_signed_in_administrator_has_no_actions_menu(self):
        other = UserFactory()
        html = self.page().content.decode()
        self.assertNotIn(f'data-modal-open="edit_role" data-user="{self.admin.public_key}"', html)
        self.assertNotIn(f'/admin-panel/deactivate/{self.admin.public_key}/', html)
        self.assertNotIn(f'aria-label="Actions for {self.admin}"', html)
        self.assertIn('<span class="data-table-tag">you</span>', html)
        self.assertIn(f'data-modal-open="edit_role" data-user="{other.public_key}"', html)
        self.assertIn(f'/admin-panel/deactivate/{other.public_key}/', html)

    def test_resend_is_offered_only_to_a_user_who_never_signed_in(self):
        invited = UserFactory()
        invited.set_unusable_password()
        invited.save()
        signed_in = UserFactory(last_login=timezone.now())
        signed_in.set_unusable_password()
        signed_in.save()
        html = self.page().content.decode()
        self.assertIn(f'/admin-panel/resend-invitation/{invited.public_key}/', html)
        self.assertNotIn(f'/admin-panel/resend-invitation/{signed_in.public_key}/', html)
        self.assertNotIn(f'/admin-panel/resend-invitation/{self.admin.public_key}/', html)

    def test_every_user_action_carries_a_confirmation(self):
        invited = UserFactory(email='invited@example.com')
        invited.set_unusable_password()
        invited.save()
        UserFactory(is_active=False)
        html = self.page().content.decode()
        self.assertIn('data-confirm-title="Deactivate User"', html)
        self.assertIn('data-confirm-title="Reactivate User"', html)
        self.assertIn('data-confirm-title="Resend Invitation"', html)
        self.assertIn('Send the invitation email to invited@example.com again?', html)
        self.assertIn('They can no longer sign in. Their projects and memberships are kept.', html)

    def test_the_user_list_is_paginated_to_25(self):
        UserFactory.create_batch(30)
        for page, expected in ((1, 25), (2, 6)):
            with self.subTest(page=page):
                self.assertEqual(len(self.page(page=page).context['user_list']), expected)

    def test_page_links_keep_the_filters(self):
        UserFactory.create_batch(30, first_name='Pat')
        response = self.page(role='user', user_q='Pat', page=2)
        self.assertContains(response, 'href="?tab=users&amp;role=user&amp;user_q=Pat&amp;page=1"')

    def test_role_links_reset_the_page(self):
        UserFactory.create_batch(30)
        response = self.page(page=2)
        self.assertContains(response, 'href="?tab=users&amp;role=viewer"')

    def test_the_users_tab_runs_a_fixed_number_of_queries(self):
        UserFactory.create_batch(2)
        self.page()
        with CaptureQueriesContext(connection) as before:
            self.page()
        UserFactory.create_batch(6)
        with CaptureQueriesContext(connection) as after:
            self.page()
        self.assertEqual(len(before), len(after))


class AdminTemplatesTabTest(TestCase):

    def setUp(self):
        self.client.force_login(AdminUserFactory())

    def page(self):
        return self.client.get('/admin-panel/?tab=templates')

    def test_visibility_pills_and_confirmed_toggles(self):
        public = TemplateFactory(name='Open Spec', is_global=True)
        private = TemplateFactory(name='Closed Spec', is_global=False)
        html = self.page().content.decode()
        self.assertIn('<span class="status-pill status-draft">Built-in</span>', html)
        self.assertIn('<span class="status-pill status-active">Public</span>', html)
        self.assertIn('<span class="status-pill status-other">Private</span>', html)
        self.assertIn(f'/admin-panel/template/{public.public_key}/toggle-visibility/" data-confirm="Make “Open Spec” private?', html)
        self.assertIn(f'/admin-panel/template/{private.public_key}/toggle-visibility/" data-confirm="Make “Closed Spec” public?', html)
        self.assertIn('data-confirm-title="Make Template Private"', html)
        self.assertIn('data-confirm-title="Make Template Public"', html)

    def test_the_templates_tab_runs_a_fixed_number_of_queries(self):
        TemplateFactory.create_batch(2)
        self.page()
        with CaptureQueriesContext(connection) as before:
            self.page()
        TemplateFactory.create_batch(6)
        with CaptureQueriesContext(connection) as after:
            self.page()
        self.assertEqual(len(before), len(after))


class AdminTagsTabTest(TestCase):

    def setUp(self):
        self.client.force_login(AdminUserFactory())

    def test_delete_is_confirmed_with_the_usage(self):
        tag = PresetTagFactory(name='Security')
        html = self.client.get('/admin-panel/?tab=tags').content.decode()
        self.assertIn(f'/admin-panel/tag-preset/{tag.public_key}/delete/" data-confirm="Delete the preset “Security”? No item uses it."', html)
        self.assertIn('data-confirm-title="Delete Tag Preset"', html)
        self.assertIn('data-modal-open="tag_preset"', html)
        ItemTagFactory(tag=tag, item=ItemFactory())
        html = self.client.get('/admin-panel/?tab=tags').content.decode()
        self.assertIn('data-confirm="Delete the preset “Security”? The tag is removed from 1 item that uses it."', html)
        ItemTagFactory(tag=tag, item=ItemFactory())
        html = self.client.get('/admin-panel/?tab=tags').content.decode()
        self.assertIn('data-confirm="Delete the preset “Security”? The tag is removed from 2 items that use it."', html)


class AdminInviteUserViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_invite_creates_user(self):
        response = self.client.post('/admin-panel/invite-user/', {
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'User',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.system_role, 'user')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['newuser@example.com'])

    def test_a_posted_role_is_ignored(self):
        self.client.post('/admin-panel/invite-user/', {
            'email': 'plain@example.com',
            'first_name': 'Plain',
            'last_name': 'User',
            'system_role': 'admin',
        })
        self.assertEqual(User.objects.get(email='plain@example.com').system_role, 'user')

    def test_invite_duplicate_email_fails(self):
        UserFactory(email='existing@example.com')
        response = self.client.post('/admin-panel/invite-user/', {
            'email': 'existing@example.com',
            'first_name': 'Dup',
            'last_name': 'User',
        })
        self.assertEqual(response.status_code, 302)

    def test_invite_duplicate_email_case_insensitive(self):
        UserFactory(email='john.doe@example.com')
        response = self.client.post('/admin-panel/invite-user/', {
            'email': 'John.Doe@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            User.objects.filter(email__iexact='john.doe@example.com').count(), 1,
        )

    def test_invite_normalizes_email_to_lowercase(self):
        self.client.post('/admin-panel/invite-user/', {
            'email': 'Alice.Smith@Example.COM',
            'first_name': 'Alice',
            'last_name': 'Smith',
        })
        user = User.objects.get(email__iexact='alice.smith@example.com')
        self.assertEqual(user.email, 'alice.smith@example.com')

    def test_non_admin_cannot_invite(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post('/admin-panel/invite-user/', {
            'email': 'new@example.com',
            'first_name': 'N',
            'last_name': 'U',
        })
        self.assertEqual(response.status_code, 403)


class AdminEditRoleViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_edit_role(self):
        user = UserFactory(system_role='user')
        response = self.client.post(f'/admin-panel/edit-role/{user.public_key}/', {
            'system_role': 'admin',
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.system_role, 'admin')

    def test_cannot_change_own_role(self):
        response = self.client.post(f'/admin-panel/edit-role/{self.admin.public_key}/', {
            'system_role': 'user',
        })
        self.assertEqual(response.status_code, 403)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.system_role, 'admin')


class AdminDeactivateUserViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_deactivate_user(self):
        user = UserFactory(is_active=True)
        response = self.client.post(f'/admin-panel/deactivate/{user.public_key}/')
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_reactivate_user(self):
        user = UserFactory(is_active=False)
        response = self.client.post(f'/admin-panel/deactivate/{user.public_key}/')
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_cannot_deactivate_self(self):
        response = self.client.post(f'/admin-panel/deactivate/{self.admin.public_key}/')
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)


class AdminTagPresetViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_created_tag_preset_is_offered_in_every_project(self):
        response = self.client.post('/admin-panel/tag-preset/create/', {
            'name': 'Accessibility',
            'color': '#dc2626',
        })
        self.assertEqual(response.status_code, 302)
        preset = Tag.objects.get(name='Accessibility', project__isnull=True)
        self.assertIn(preset, Tag.for_project(ProjectFactory()))

    def test_delete_tag_preset(self):
        tag = PresetTagFactory(name='OldTag')
        response = self.client.post(f'/admin-panel/tag-preset/{tag.public_key}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())


class AdminTemplateToggleVisibilityViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_toggle_private_to_public(self):
        template = TemplateFactory(is_global=False)
        response = self.client.post(f'/admin-panel/template/{template.public_key}/toggle-visibility/')
        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertTrue(template.is_global)

    def test_toggle_public_to_private(self):
        template = TemplateFactory(is_global=True)
        response = self.client.post(f'/admin-panel/template/{template.public_key}/toggle-visibility/')
        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertFalse(template.is_global)

    def test_cannot_toggle_builtin(self):
        template = TemplateFactory(is_builtin=True, is_global=True)
        response = self.client.post(f'/admin-panel/template/{template.public_key}/toggle-visibility/')
        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertTrue(template.is_global)

    def test_non_admin_gets_403(self):
        user = UserFactory()
        self.client.force_login(user)
        template = TemplateFactory(is_global=False)
        response = self.client.post(f'/admin-panel/template/{template.public_key}/toggle-visibility/')
        self.assertEqual(response.status_code, 403)


class AdminSystemSettingsViewTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def test_save_general_settings(self):
        response = self.client.post('/admin-panel/system-settings/', {
            'form_type': 'general',
            'org_name': 'My Org',
            'max_attachment_size_mb': 25,
        })
        self.assertRedirects(response, '/admin-panel/?tab=system', fetch_redirect_response=False)
        settings = SystemSettings.load()
        self.assertEqual(settings.org_name, 'My Org')
        self.assertEqual(settings.max_attachment_size_mb, 25)

    def test_the_removed_settings_are_not_offered_or_saved(self):
        html = self.client.get('/admin-panel/?tab=system').content.decode()
        self.assertNotIn('default_user_role', html)
        self.assertNotIn('max_projects_per_user', html)
        self.assertEqual(html.count('data-dirty-form'), 3)
        self.assertIn('data-depends-on="id_auto_archive_enabled"', html)
        self.assertIn('data-depends-on="id_auto_delete_archived"', html)
        response = self.client.post('/admin-panel/system-settings/', {'form_type': 'storage', 'max_attachment_size_mb': 25})
        self.assertEqual(messages_of(response), ['Invalid form type.'])
        self.assertEqual(SystemSettings.load().max_attachment_size_mb, 10)

    def test_save_archiving_settings(self):
        response = self.client.post('/admin-panel/system-settings/', {
            'form_type': 'archiving',
            'auto_archive_enabled': 'on',
            'auto_archive_days': 30,
            'auto_delete_days': 400,
        })
        self.assertRedirects(response, '/admin-panel/?tab=system', fetch_redirect_response=False)
        settings = SystemSettings.load()
        self.assertEqual((settings.auto_archive_enabled, settings.auto_archive_days), (True, 30))
        self.assertEqual((settings.allow_user_restore, settings.auto_delete_archived, settings.auto_delete_days), (False, False, 400))


@override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_CONFIGURED)
class AdminAuthenticationSettingsTest(TestCase):

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client.force_login(self.admin)

    def save(self, **flags):
        return self.client.post('/admin-panel/system-settings/', {'form_type': 'authentication', **flags})

    def stored(self):
        stored = SystemSettings.load()
        return stored.entra_login_enabled, stored.password_login_enabled

    def test_the_card_renders_with_the_defaults_and_microsoft_configured(self):
        response = self.client.get('/admin-panel/?tab=system')
        self.assertContains(response, 'value="authentication"')
        form = response.context['authentication_form']
        self.assertTrue(form.entra_configured)
        self.assertEqual((form['entra_login_enabled'].value(), form['password_login_enabled'].value()), (True, False))
        self.assertNotContains(response, 'not configured in this environment')
        self.assertNotIn('disabled', str(form['entra_login_enabled']))

    def test_save_authentication_settings(self):
        response = self.save(entra_login_enabled='on', password_login_enabled='on')
        self.assertRedirects(response, '/admin-panel/?tab=system', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), ['System settings saved.'])
        self.assertEqual(self.stored(), (True, True))
        self.save(password_login_enabled='on')
        self.assertEqual(self.stored(), (False, True))
        self.save(entra_login_enabled='on')
        self.assertEqual(self.stored(), (True, False))

    def test_both_off_is_refused(self):
        set_methods(True, True)
        response = self.save()
        self.assertRedirects(response, '/admin-panel/?tab=system', fetch_redirect_response=False)
        self.assertEqual(messages_of(response), ['At least one sign-in method must stay on.'])
        self.assertEqual(self.stored(), (True, True))

    def test_the_database_refuses_both_off(self):
        set_methods(True, True)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SystemSettings.objects.filter(pk=1).update(entra_login_enabled=False, password_login_enabled=False)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SystemSettings(pk=1, entra_login_enabled=False, password_login_enabled=False).save()
        self.assertEqual(self.stored(), (True, True))

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_entra_on_while_not_configured_is_refused(self):
        set_methods(True, True)
        response = self.save(entra_login_enabled='on', password_login_enabled='on')
        self.assertEqual(messages_of(response), ['Microsoft sign-in cannot be turned on: it is not configured in this environment.'])
        self.assertEqual(self.stored(), (True, True))

    @override_settings(SOCIALACCOUNT_PROVIDERS=ENTRA_UNCONFIGURED)
    def test_the_microsoft_row_is_disabled_and_marked_when_not_configured(self):
        response = self.client.get('/admin-panel/?tab=system')
        self.assertContains(response, 'not configured in this environment')
        form = response.context['authentication_form']
        self.assertFalse(form.entra_configured)
        self.assertFalse(form['entra_login_enabled'].value())
        self.assertIn('disabled', str(form['entra_login_enabled']))
        self.save(password_login_enabled='on')
        self.assertEqual(self.stored(), (False, True))

    def test_non_admin_gets_403(self):
        self.client.force_login(UserFactory())
        self.assertEqual(self.save(password_login_enabled='on').status_code, 403)
        self.assertEqual(self.stored(), (True, False))
